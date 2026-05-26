"""Утилита поиска по базе — используется агентами и из терминала.

Примеры:
    python query.py --text "эскроу"
    python query.py --text "акция" --days 14 --limit 30
    python query.py --tag developer:ПИК --days 30
    python query.py --tag zhk:Republic
    python query.py --channels
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import config
from db import DB


def cmd_text(args, db: DB):
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    rows = db.conn.execute(
        """SELECT p.date, c.title AS channel, c.username, p.url, p.text
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN posts_fts f ON f.rowid = p.id
           WHERE posts_fts MATCH ? AND p.date >= ? AND p.canonical_id IS NULL
           ORDER BY p.date DESC LIMIT ?""",
        (args.text, since, args.limit),
    ).fetchall()
    for r in rows:
        src = f"@{r['username']}" if r['username'] else r['channel']
        print(f"\n[{r['date'][:16]}] {src}")
        print(f"  {r['text'][:400]}")
        if r['url']:
            print(f"  {r['url']}")


def cmd_tag(args, db: DB):
    kind, _, value = args.tag.partition(":")
    if not value:
        print("✗ Тег должен быть в формате kind:value (например developer:ПИК)")
        return 1
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    rows = db.conn.execute(
        """SELECT p.date, c.title AS channel, c.username, p.url, p.text
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE t.kind = ? AND t.value = ? AND p.date >= ? AND p.canonical_id IS NULL
           ORDER BY p.date DESC LIMIT ?""",
        (kind, value, since, args.limit),
    ).fetchall()
    for r in rows:
        src = f"@{r['username']}" if r['username'] else r['channel']
        print(f"\n[{r['date'][:16]}] {src}")
        print(f"  {r['text'][:400]}")
        if r['url']:
            print(f"  {r['url']}")


def cmd_channels(args, db: DB):
    rows = db.conn.execute(
        "SELECT title, username, is_chat, folder FROM channels ORDER BY folder, title"
    ).fetchall()
    for r in rows:
        flag = "[ЧАТ]" if r['is_chat'] else "[КАН]"
        un = f"@{r['username']}" if r['username'] else "—"
        print(f"  {flag} {r['title']} ({un})  [{r['folder']}]")
    print(f"\nВсего: {len(rows)}")


def cmd_stats(args, db: DB):
    total = db.conn.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"]
    processed = db.conn.execute("SELECT COUNT(*) AS n FROM posts WHERE processed=1").fetchone()["n"]
    canonical = db.conn.execute("SELECT COUNT(*) AS n FROM posts WHERE canonical_id IS NULL AND processed=1").fetchone()["n"]
    dups = db.conn.execute("SELECT COUNT(*) AS n FROM posts WHERE canonical_id IS NOT NULL").fetchone()["n"]
    with_tags = db.conn.execute("SELECT COUNT(DISTINCT post_id) AS n FROM post_tags").fetchone()["n"]
    last_run = db.conn.execute(
        "SELECT started_at, finished_at, posts_new, posts_seen FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    print(f"Постов в базе: {total}")
    print(f"  обработано:           {processed}")
    print(f"  с тегами (релевант.): {with_tags}")
    print(f"  canonical (уникальн): {canonical}")
    print(f"  помечено дублями:     {dups}")
    if last_run:
        print(f"Последний запуск: {last_run['started_at']} → {last_run['finished_at']}")
        print(f"  новых: {last_run['posts_new']}, просмотрено: {last_run['posts_seen']}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="query.py")
    parser.add_argument("--text", help="Полнотекстовый поиск (FTS5)")
    parser.add_argument("--tag", help="Поиск по тегу kind:value")
    parser.add_argument("--days", type=int, default=30, help="Глубина поиска в днях (default: 30)")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--channels", action="store_true", help="Список всех каналов")
    parser.add_argument("--stats", action="store_true", help="Статистика базы")
    args = parser.parse_args()

    db = DB(config.DB_PATH)
    try:
        if args.channels:
            cmd_channels(args, db)
        elif args.stats:
            cmd_stats(args, db)
        elif args.tag:
            return cmd_tag(args, db) or 0
        elif args.text:
            cmd_text(args, db)
        else:
            parser.print_help()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
