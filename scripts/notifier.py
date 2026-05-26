"""Алерты по важным событиям через Telegram Bot API.

Логика:
  1. После processor.py запускается этот скрипт
  2. Берёт релевантные посты за последние 24ч с importance >= ALERT_IMPORTANCE_THRESHOLD
  3. Фильтрует те, что уже были отправлены (db.notifications)
  4. Отправляет каждый в TELEGRAM_BOT_CHAT_ID через @IGDeveloper_bot
  5. Помечает как notified

Запуск: python notifier.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import bot
import config
from db import DB


def short_text(text: str, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def format_alert(row: dict) -> tuple[str, list[list[dict]]]:
    """Возвращает (текст, inline-кнопки) для отправки через bot.send_message."""
    date_short = row["date"][:16].replace("T", " ")
    channel = f"@{row['username']}" if row["username"] else row["channel"]
    summary = short_text(row["text"], 700)
    url = row["url"] or ""

    importance = int(row["importance"] or 3)
    stars = "⭐" * max(1, min(importance, 5))

    parts = [f"🚨 <b>Важное на рынке</b>  {stars}", "", bot.html_escape(summary), ""]

    meta = []
    if row["developers"]:
        meta.append(f"🏗 {bot.html_escape(row['developers'])}")
    if row["zhk"]:
        meta.append(f"🏢 ЖК: {bot.html_escape(row['zhk'])}")
    if row["topics"]:
        meta.append(f"📌 {bot.html_escape(row['topics'])}")
    if meta:
        parts.extend(meta)
        parts.append("")

    parts.append(f"📅 {date_short} · {bot.html_escape(channel)}")

    text = "\n".join(parts)
    buttons = [[{"text": "📨 Открыть пост в Telegram", "url": url}]] if url else None
    return text, buttons


def fetch_alerts(db: DB, threshold: int, hours: int = 24) -> list[dict]:
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
           WHERE p.processed = 1
             AND p.date >= ?
             AND p.canonical_id IS NULL
             AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.post_id = p.id)
           GROUP BY p.id
           HAVING importance >= ?
           ORDER BY importance DESC, p.date DESC
           LIMIT 20""",
        (since, threshold),
    )
    return [dict(r) for r in cur.fetchall()]


def main() -> int:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
    threshold = int(config.env("ALERT_IMPORTANCE_THRESHOLD", "4"))

    db = DB(config.DB_PATH)
    alerts = fetch_alerts(db, threshold=threshold, hours=24)

    if not alerts:
        print("[notifier] Нечего отправлять — важных событий за сутки нет.")
        db.close()
        return 0

    print(f"[notifier] К отправке: {len(alerts)} алертов")

    sent = 0
    for alert in alerts:
        try:
            text, buttons = format_alert(alert)
            bot.send_message(chat_id, text, buttons=buttons)
            db.mark_notified(alert["id"], kind="alert")
            sent += 1
        except Exception as exc:
            print(f"  ✗ Не удалось отправить алерт {alert['id']}: {exc}")

    print(f"[notifier] ✓ Отправлено: {sent}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
