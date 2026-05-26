"""Sentiment-анализ рынка: «температура» за период через LLM.

Что внутри:
  1. Берём релевантные посты за последние N дней (по умолчанию 7)
  2. Сравниваем с предыдущим периодом такого же объёма
  3. Передаём в Claude — он оценивает настроение / тренды
  4. Возвращаем структурированный анализ

Использование:
  python sentiment.py            # вывод в stdout, период 7 дней
  python sentiment.py --send     # шлёт в Telegram
  python sentiment.py --days 14  # период 14 дней
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic

import bot
import config
from db import DB


SYSTEM_PROMPT = """Ты — аналитик рынка недвижимости Москвы. Твоя задача — оценить «температуру» рынка по постам из профильных Telegram-каналов за период.

Тебе передадут два набора фактов: ТЕКУЩИЙ период и ПРЕДЫДУЩИЙ (для сравнения).

Сформируй короткий, плотный анализ в формате Telegram HTML:

🌡 <b>Температура рынка · &lt;период&gt;</b>

<b>📊 Общая оценка</b>
Одно ёмкое предложение: рост / стабильность / охлаждение / настороженность / перегрев. С обоснованием в 1 предложении.

<b>🔥 Что разгоняет рынок</b>
3-4 буллета — конкретные движения которые двигают рынок ВВЕРХ или поддерживают активность. По 1 строке.

<b>❄️ Что сдерживает / охлаждает</b>
2-3 буллета — что замедляет, какие риски/ограничения видны.

<b>📈 Изменения недели</b>
Что появилось нового / что усилилось / что ослабло по сравнению с прошлым периодом. 2-3 строки.

<b>🎯 Что это значит для эксперта</b>
1-2 предложения практической пользы: что обсуждать с клиентами, на что обращать внимание, какие риски проговаривать.

Правила:
1. Только факты — без общих рассуждений и общих фраз ("рынок недвижимости остаётся важным")
2. Цифры и названия — из переданных данных
3. Сравнение «было/стало» — только если данные позволяют, иначе пропускай
4. Тон — спокойный, аналитический, без инфо-шума и без воды
5. Не используй markdown — только Telegram HTML (<b>, <i>)
6. Без приветствий, без подписи
"""


def fetch_period_summary(db: DB, since_iso: str, until_iso: str) -> str:
    """Возвращает текстовое описание периода — 1 строка на факт, отсортировано по важности."""
    cur = db.conn.execute(
        """SELECT p.date, p.text,
                  c.username,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='bc' THEN t.value END) AS bc,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='topic' THEN t.value END) AS topics
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.canonical_id IS NULL
             AND p.date >= ? AND p.date < ?
           GROUP BY p.id
           ORDER BY importance DESC, p.date DESC
           LIMIT 80""",
        (since_iso, until_iso),
    )
    rows = cur.fetchall()
    lines = []
    for r in rows:
        devs = (r["developers"] or "").replace(",", ", ")
        zhk = (r["zhk"] or "").replace(",", ", ")
        bc = (r["bc"] or "").replace(",", ", ")
        topics = (r["topics"] or "").replace(",", ", ")
        entities = " · ".join(filter(None, [devs, zhk, bc])) or "—"
        text = " ".join((r["text"] or "").split())[:280]
        lines.append(f"{r['date'][:10]} ⭐{r['importance'] or 3} [{topics}] [{entities}] — {text}")
    return "\n".join(lines) if lines else "Нет фактов за период."


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--send", action="store_true")
    cli.add_argument("--days", type=int, default=7)
    args = cli.parse_args()

    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    db = DB(config.DB_PATH)

    now = datetime.now(timezone.utc)
    cur_start = now - timedelta(days=args.days)
    prev_start = now - timedelta(days=args.days * 2)

    current = fetch_period_summary(db, cur_start.isoformat(), now.isoformat())
    previous = fetch_period_summary(db, prev_start.isoformat(), cur_start.isoformat())

    if current.startswith("Нет фактов"):
        text = "<b>🌡 Температура рынка</b>\n\nНедостаточно данных для анализа за последние дни."
    else:
        period_label = f"{cur_start.strftime('%d.%m')}—{now.strftime('%d.%m.%Y')}"
        user_msg = (
            f"Период анализа: {period_label} ({args.days} дней)\n\n"
            f"=== ТЕКУЩИЙ ПЕРИОД ===\n{current}\n\n"
            f"=== ПРЕДЫДУЩИЙ ПЕРИОД (для сравнения) ===\n{previous}\n\n"
            f"Сформируй анализ температуры рынка по правилам из системного промпта."
        )
        client = Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))
        print(f"[sentiment] Текущий период: ~{current.count(chr(10))} фактов, "
              f"предыдущий: ~{previous.count(chr(10))} фактов. LLM-запрос ({model})...")
        resp = client.messages.create(
            model=model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))

    print(f"[sentiment] Размер ответа: {len(text)} символов")

    if args.send:
        chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
        bot.send_message(chat_id, text)
        print(f"[sentiment] ✓ Отправлено в чат {chat_id}")
    else:
        print()
        print(text)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
