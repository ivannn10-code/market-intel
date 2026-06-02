"""Парсинг постов из Telegram-каналов.

Режимы:
    python parser.py                       # ежедневный (LOOKBACK_HOURS из .env, default 26)
    python parser.py --hours 360           # бэкфил за 15 дней
    python parser.py --days 30             # бэкфил за 30 дней
    python parser.py --days 30 --sleep 5   # с паузой 5 сек между каналами (для FloodWait)
    python parser.py --limit 2000          # не более 2000 сообщений с канала

Все посты дедуплицируются по (channel_id, tg_msg_id).
Сохраняются в SQLite + дублируются в raw/YYYY-MM-DD.jsonl как страховка.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

import config
from db import DB


def post_url(channel_username: str | None, channel_id: int, msg_id: int) -> str:
    if channel_username:
        return f"https://t.me/{channel_username}/{msg_id}"
    # Для приватных каналов формат t.me/c/<internal_id>/<msg_id>
    # channel_id в Telethon отрицательный (-100xxxxxxxx); внутренний id — без префикса -100
    raw = str(channel_id).removeprefix("-100")
    return f"https://t.me/c/{raw}/{msg_id}"


def text_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())[:2000]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


async def fetch_channel(client: TelegramClient, db: DB, channel_row, since: datetime, raw_fp, per_channel_limit: int) -> tuple[int, int]:
    """Возвращает (новых постов, всего просмотрено)."""
    new_count = 0
    seen_count = 0

    try:
        entity = await client.get_entity(channel_row["tg_id"])
    except Exception as exc:
        print(f"  ✗ {channel_row['title']}: get_entity failed: {exc}")
        return 0, 0

    try:
        async for msg in client.iter_messages(entity, limit=per_channel_limit):
            if msg.date is None:
                continue
            msg_date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
            if msg_date < since:
                break
            seen_count += 1

            text = (msg.text or msg.message or "").strip()
            if not text:
                # Пропускаем посты без текста (только фото/видео без подписи)
                continue
            if len(text) < 20:
                continue

            h = text_hash(text)
            views = getattr(msg, "views", None)
            forwards = getattr(msg, "forwards", None)
            reply_to = msg.reply_to_msg_id if msg.reply_to else None
            has_media = msg.media is not None
            url = post_url(channel_row["username"], channel_row["tg_id"], msg.id)

            new_id = db.insert_post(
                channel_id=channel_row["id"],
                tg_msg_id=msg.id,
                date=msg_date.isoformat(),
                text=text,
                text_hash=h,
                views=views,
                forwards=forwards,
                reply_to=reply_to,
                has_media=has_media,
                url=url,
            )
            if new_id is not None:
                new_count += 1
                raw_fp.write(json.dumps({
                    "id": new_id,
                    "channel_id": channel_row["id"],
                    "channel_title": channel_row["title"],
                    "channel_username": channel_row["username"],
                    "tg_msg_id": msg.id,
                    "date": msg_date.isoformat(),
                    "text": text,
                    "url": url,
                    "views": views,
                    "forwards": forwards,
                }, ensure_ascii=False) + "\n")
    except FloodWaitError as exc:
        print(f"  ⏸ FloodWait {exc.seconds}s на {channel_row['title']} — жду")
        await asyncio.sleep(exc.seconds + 1)
    except Exception as exc:
        print(f"  ✗ {channel_row['title']}: {exc}")

    return new_count, seen_count


async def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--hours", type=int, help="Глубина в часах (приоритет над --days и LOOKBACK_HOURS)")
    cli.add_argument("--days", type=int, help="Глубина в днях (для бэкфила)")
    cli.add_argument("--sleep", type=float, default=0.0, help="Пауза между каналами в секундах (для бэкфила рекомендуется 3-5)")
    cli.add_argument("--limit", type=int, default=500, help="Макс. сообщений на канал (для бэкфила можно 5000-10000)")
    args = cli.parse_args()

    api_id = int(config.env("TELEGRAM_API_ID", required=True))
    api_hash = config.env("TELEGRAM_API_HASH", required=True)
    phone = config.env("TELEGRAM_PHONE", required=True)

    if args.hours is not None:
        lookback_hours = args.hours
    elif args.days is not None:
        lookback_hours = args.days * 24
    else:
        lookback_hours = int(config.env("LOOKBACK_HOURS", "26"))

    if not config.SESSION_PATH.exists():
        print(f"✗ session-файл не найден: {config.SESSION_PATH}. Сначала запусти init.py")
        return 2

    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    date_str = datetime.now().strftime("%Y-%m-%d")
    raw_path = config.RAW_DIR / f"{date_str}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    db = DB(config.DB_PATH)
    run_id = db.start_run()

    channels = db.conn.execute(
        "SELECT id, tg_id, username, title FROM channels WHERE is_active=1 ORDER BY title"
    ).fetchall()
    if not channels:
        print("✗ В БД нет каналов. Сначала запусти init.py")
        db.finish_run(run_id, 0, 0, "no_channels")
        db.close()
        return 3

    print(f"[parser] Каналов: {len(channels)}, окно: {lookback_hours}ч (с {since.isoformat()}), лимит/канал: {args.limit}, пауза: {args.sleep}с")

    client = TelegramClient(str(config.SESSION_PATH), api_id, api_hash)
    await client.start(phone=phone)

    total_new = 0
    total_seen = 0
    errors: list[str] = []

    with open(raw_path, "a", encoding="utf-8") as raw_fp:
        for i, ch in enumerate(channels):
            try:
                n, s = await fetch_channel(client, db, ch, since, raw_fp, args.limit)
                if n > 0:
                    print(f"  [{i+1}/{len(channels)}] • {ch['title']}: +{n} новых")
                total_new += n
                total_seen += s
                if args.sleep > 0 and i < len(channels) - 1:
                    await asyncio.sleep(args.sleep)
            except Exception:
                err = f"{ch['title']}: {traceback.format_exc(limit=2)}"
                errors.append(err)
                print(f"  ✗ {err}")

    db.finish_run(run_id, total_new, total_seen, "\n---\n".join(errors) if errors else None)
    print(f"[parser] ✓ Готово. Новых постов: {total_new}, просмотрено: {total_seen}")
    print(f"[parser] ✓ Raw-архив: {raw_path}")

    db.close()
    await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
