"""Итоги недели в рынке недвижимости — структурированная сводка через LLM.

Что внутри:
  1. Берём все relevant canonical-посты за последние 7 дней
  2. Группируем по 4 ключевым направлениям (акции / старты / ипотека / коммерция)
  3. Извлекаем топ-N по importance в каждом блоке
  4. Передаём в Claude Sonnet, который делает структурированный обзор недели
  5. Возвращаем готовый текст (HTML для Telegram)

Использование:
  python weekly_digest.py            # вывод в stdout
  python weekly_digest.py --send     # сразу шлёт в TELEGRAM_BOT_CHAT_ID
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic

import bot
import config
from db import DB

SECTIONS = [
    ("akcii-zastroyshchikov", "💰 АКЦИИ И СКИДКИ", 10),
    ("novostroyki-launch", "🏗 СТАРТЫ ПРОДАЖ", 6),
    ("ipoteka-stavka", "📈 ИПОТЕКА И СТАВКА", 5),
    ("kommerciya-bc", "🏢 КОММЕРЦИЯ (БЦ класса А)", 5),
    ("makroekonomika", "📜 МАКРО, ЗАКОНЫ, ЭСКРОУ", 4),
    ("analitika-rynka", "📊 АНАЛИТИКА РЫНКА", 4),
]

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

SYSTEM_PROMPT = """Ты — аналитик рынка недвижимости Москвы. Работаешь на премиум-эксперта по новостройкам бизнес-класса и коммерческой недвижимости класса А.

Сейчас тебе дадут сырые факты за прошедшую неделю из профильных Telegram-каналов. Сформируй из них СТРУКТУРИРОВАННЫЙ обзор недели для эксперта-практика (он будет использовать это для контента и переговоров с клиентами).

Формат вывода — Telegram HTML с разметкой <b>, <i>, <a>:

📊 <b>ИТОГИ НЕДЕЛИ · &lt;даты&gt;</b>

🎯 <b>Главное</b>
2-3 предложения о ключевых движениях недели. Цифры в фокусе.

💰 <b>Акции и скидки</b>
• <b>Застройщик/ЖК</b> — суть в 1 строке (макс 100 символов)
[5-6 пунктов, отсортированных по значимости]

🏗 <b>Старты продаж и новые корпуса</b>
• <b>ЖК + застройщик</b> — что запустилось
[3-4 пункта]

📈 <b>Ипотека и ставка</b>
2-3 строки текстом — что изменилось

🏢 <b>Коммерция</b>
2-3 строки текстом — главное в БЦ

🌡 <b>Температура рынка</b>
1-2 предложения: рост/стабильность/настороженность + ключевая причина

Правила:
1. ТОЛЬКО факты из переданных данных — никаких выдумок, никаких общих рассуждений
2. Каждая цифра/название — из исходного факта
3. Не дублируй одно событие в разных блоках
4. Тон — экспертный, без воды и без инфоцыганщины
5. Не используй markdown (только Telegram HTML)
6. Без приветствий, без подписи в конце — только сам обзор
"""


def fetch_week_facts(db: DB, days: int = 7) -> dict[str, list[dict]]:
    """Возвращает {topic_slug: [{date, channel, text, devs, zhk, bc, importance}, ...]}."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = db.conn.execute(
        """SELECT p.id, p.date, p.text, p.url,
                  c.title AS channel, c.username,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='bc' THEN t.value END) AS bc
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.canonical_id IS NULL AND p.date >= ?
           GROUP BY p.id
           ORDER BY p.date DESC""",
        (since,),
    )
    facts = [dict(r) for r in cur.fetchall()]

    # Группируем по теме (одна запись может попасть в несколько групп)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        # Достаём темы для конкретного поста
        topics_cur = db.conn.execute(
            """SELECT t.value FROM post_tags pt JOIN tags t ON t.id = pt.tag_id
               WHERE pt.post_id = ? AND t.kind = 'topic'""",
            (f["id"],),
        )
        topics = [r[0] for r in topics_cur.fetchall()]
        for t in topics:
            by_topic[t].append(f)

    # Сортируем внутри каждой темы по importance ↓ затем по дате ↓
    for t in by_topic:
        by_topic[t].sort(key=lambda x: (-(x["importance"] or 0), x["date"]), reverse=False)
        # importance DESC, date ASC; перевернём для date DESC
        by_topic[t].sort(key=lambda x: x["date"], reverse=True)
        by_topic[t].sort(key=lambda x: x["importance"] or 0, reverse=True)

    return by_topic


def build_context_for_llm(by_topic: dict[str, list[dict]]) -> str:
    """Формирует структурированный input для Claude — топ-N в каждом блоке."""
    parts = []
    for slug, title, limit in SECTIONS:
        items = by_topic.get(slug, [])[:limit]
        if not items:
            continue
        parts.append(f"\n=== {title} ({slug}) ===\n")
        for i, f in enumerate(items, 1):
            devs = (f["developers"] or "").replace(",", ", ")
            zhk = (f["zhk"] or "").replace(",", ", ")
            bc = (f["bc"] or "").replace(",", ", ")
            entities = " · ".join(filter(None, [devs, zhk, bc]))
            entities_md = f" [{entities}]" if entities else ""
            text = " ".join((f["text"] or "").split())[:400]
            parts.append(f"{i}. {f['date'][:10]} ⭐{f['importance'] or 3}{entities_md} — {text}")
    return "\n".join(parts)


def call_llm(client: Anthropic, model: str, week_context: str, date_range: str) -> str:
    user_msg = (
        f"Период: {date_range}\n\n"
        f"Факты за неделю (отсортированы по важности внутри каждого блока):\n"
        f"{week_context}\n\n"
        f"Сформируй структурированный обзор недели по правилам из системного промпта."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(b.text for b in resp.content if hasattr(b, "text"))


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--send", action="store_true", help="Отправить в Telegram")
    cli.add_argument("--days", type=int, default=7)
    args = cli.parse_args()

    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    db = DB(config.DB_PATH)

    by_topic = fetch_week_facts(db, days=args.days)
    total_facts = sum(len(v) for v in by_topic.values())

    if total_facts == 0:
        text = "<b>📊 Итоги недели</b>\n\nЗа последние 7 дней значимых событий на рынке не зафиксировано."
    else:
        today = datetime.now()
        start = today - timedelta(days=args.days)
        date_range = f"{start.strftime('%d.%m')}—{today.strftime('%d.%m.%Y')}"

        ctx = build_context_for_llm(by_topic)
        client = Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))
        print(f"[weekly] Фактов в контексте: ~{sum(min(len(v), s[2]) for v, s in zip(by_topic.values(), SECTIONS))}, "
              f"LLM-запрос ({model})...")
        text = call_llm(client, model, ctx, date_range)

    print(f"[weekly] Размер ответа: {len(text)} символов")

    if args.send:
        chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
        bot.send_message(chat_id, text)
        print(f"[weekly] ✓ Отправлено в чат {chat_id}")
    else:
        print()
        print(text)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
