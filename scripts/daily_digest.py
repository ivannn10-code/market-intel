"""Утренняя сводка рынка в Telegram через Bot API.

Берёт релевантные посты за последние ~24 часа и отправляет читабельный дайджест
в TELEGRAM_BOT_CHAT_ID через @IGDeveloper_bot.

Запуск: python daily_digest.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bot
import config
from db import DB

# Порядок тем в дайджесте + emoji + сколько фактов брать
TOPIC_ORDER = [
    ("akcii-zastroyshchikov", "💰 Акции и скидки застройщиков", 5),
    ("novostroyki-launch", "🏗 Старты продаж и новые корпуса", 5),
    ("ipoteka-stavka", "📈 Ипотека, рассрочка, ставка ЦБ", 3),
    ("kommerciya-bc", "🏢 Коммерция: БЦ класса А", 3),
    ("makroekonomika", "📜 Макро, законы, эскроу", 3),
    ("analitika-rynka", "📊 Аналитика рынка", 3),
]

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def fetch_facts(db: DB, hours: int = 26) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cur = db.conn.execute(
        """SELECT p.id, p.date, p.text, p.url,
                  c.title AS channel, c.username,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='topic' THEN t.value END) AS topics
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.date >= ? AND p.canonical_id IS NULL
           GROUP BY p.id
           ORDER BY importance DESC, p.date DESC""",
        (since,),
    )
    return [dict(r) for r in cur.fetchall()]


def short_text(text: str, limit: int = 280) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def fact_block(fact: dict) -> str:
    """Один факт = 3 строки:
       ⭐⭐⭐⭐ Застройщик(и)
       Краткое содержание
       📨 @channel · открыть пост ↗   ← вся строка кликабельна
    """
    importance = int(fact["importance"] or 3)
    stars = "⭐" * max(1, min(importance, 5))
    summary = bot.html_escape(short_text(fact["text"], 280))
    url = fact["url"] or ""
    devs = bot.html_escape(fact["developers"] or "")
    devs_md = f"  <i>{devs}</i>" if devs else ""
    channel = f"@{fact['username']}" if fact["username"] else fact["channel"]
    channel_html = bot.html_escape(channel)

    return (
        f"{stars}{devs_md}\n"
        f"{summary}\n"
        f'📨 <a href="{url}">{channel_html} · открыть пост ↗</a>'
    )


def build_digest(facts: list[dict]) -> str:
    today = datetime.now()
    weekday = WEEKDAYS[today.weekday()]
    header = f"📊 <b>Дайджест рынка · {today.strftime('%d.%m.%Y')} ({weekday})</b>\n\nВсего фактов за сутки: <b>{len(facts)}</b>"

    if not facts:
        return header + "\n\nЗа сутки ничего значимого не зафиксировано."

    by_topic: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        topics = (f["topics"] or "").split(",") if f["topics"] else []
        for t in topics:
            t = t.strip()
            if t:
                by_topic[t].append(f)

    lines = [header]

    def add_section(title: str, items: list[dict]):
        if not items:
            return
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"<b>{title}</b>")
        for f in items:
            lines.append("")
            lines.append(fact_block(f))

    # Главное
    main = [f for f in facts if (f["importance"] or 0) >= 4][:5]
    main_ids = {f["id"] for f in main}
    if main:
        add_section("🚨 Главное", main)

    for slug, title, limit in TOPIC_ORDER:
        items = [f for f in by_topic.get(slug, []) if f["id"] not in main_ids]
        items.sort(key=lambda x: (x["importance"] or 0), reverse=True)
        add_section(title, items[:limit])

    return "\n".join(lines)


def main() -> int:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)

    db = DB(config.DB_PATH)
    facts = fetch_facts(db, hours=26)
    text = build_digest(facts)

    print(f"[digest] Фактов за сутки: {len(facts)}, размер сообщения: {len(text)} симв.")

    try:
        bot.send_message(chat_id, text)
        print(f"[digest] ✓ Отправлено в чат {chat_id}")
    except Exception as exc:
        print(f"[digest] ✗ Ошибка отправки: {exc}")
        db.close()
        return 1

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
