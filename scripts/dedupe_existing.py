"""Миграция существующих 1700 постов: считает fingerprint и помечает дубли.

Логика:
  1. Для каждого processed=1 поста с relevant-тегами берём developers/zhk/bc/topic
  2. Считаем fingerprint = (норм.застройщики | норм.объекты | первая_тема | день)
  3. Группируем по fingerprint, в каждой группе самый ранний по дате = canonical, остальные = дубли
  4. Записываем в БД: posts.fingerprint и posts.canonical_id

После этого daily_digest и notifier фильтруют canonical_id IS NULL и шум падает в 2-3 раза.

Запуск: python dedupe_existing.py
        python dedupe_existing.py --dry-run    # только показать статистику, не менять БД
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

import config
from db import DB


def normalize_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[«»\"\'`,.]", "", n)
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"^(жк|гк|группа|зк|клубный дом|кд)\s+", "", n)
    return n.strip()


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--dry-run", action="store_true", help="Только показать статистику без изменения БД")
    args = cli.parse_args()

    db = DB(config.DB_PATH)

    # Берём все relevant-посты (те, у кого есть хоть один тег topic) с их тегами
    print("[dedupe] Собираю данные из БД...")
    cur = db.conn.execute(
        """SELECT p.id, p.date, p.text, c.username,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='bc' THEN t.value END) AS bc,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='topic' THEN t.value END) AS topics
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.canonical_id IS NULL
           GROUP BY p.id
           HAVING topics IS NOT NULL AND topics != ''"""
    )
    rows = cur.fetchall()
    print(f"[dedupe] Постов с тегами: {len(rows)}")

    # Группируем по fingerprint
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped_no_fp = 0
    for r in rows:
        devs_raw = (r["developers"] or "").split(",") if r["developers"] else []
        zhk_raw = (r["zhk"] or "").split(",") if r["zhk"] else []
        bc_raw = (r["bc"] or "").split(",") if r["bc"] else []
        topics_raw = (r["topics"] or "").split(",") if r["topics"] else []

        devs = sorted(set(normalize_name(d) for d in devs_raw if d.strip()))
        objects = sorted(set(normalize_name(z) for z in (zhk_raw + bc_raw) if z.strip()))
        primary_topic = topics_raw[0].strip() if topics_raw else "other"
        day = r["date"][:10]

        if not devs and not objects:
            skipped_no_fp += 1
            continue

        fp = f"{'|'.join(devs)}::{'|'.join(objects)}::{primary_topic}::{day}"
        groups[fp].append({
            "id": r["id"],
            "date": r["date"],
            "text": r["text"][:80],
            "channel": r["username"],
        })

    print(f"[dedupe] Постов без fingerprint (нет ни ЖК ни застройщика): {skipped_no_fp}")
    print(f"[dedupe] Уникальных fingerprint групп: {len(groups)}")

    # Считаем сколько будет помечено дублями
    n_canonical = 0
    n_dups = 0
    samples = []
    for fp, posts in groups.items():
        posts.sort(key=lambda x: x["date"])  # canonical = самый ранний
        n_canonical += 1
        n_dups += len(posts) - 1
        if len(posts) > 1 and len(samples) < 5:
            samples.append((fp, posts))

    print(f"[dedupe] Canonical постов: {n_canonical}")
    print(f"[dedupe] Будет помечено дублями: {n_dups}")
    print()
    if samples:
        print("Примеры найденных дублей:")
        for fp, posts in samples:
            print(f"\n  fingerprint: {fp}")
            for p in posts:
                marker = "✓ CANONICAL" if p == posts[0] else "  → dup"
                print(f"    {marker}  [@{p['channel'] or '?'}] {p['date'][:16]}  {p['text']}...")
        print()

    if args.dry_run:
        print("[dedupe] --dry-run: БД не меняется.")
        db.close()
        return 0

    # Применяем
    print("[dedupe] Применяю в БД...")
    n_applied = 0
    for fp, posts in groups.items():
        canonical = posts[0]
        # Записываем fingerprint для canonical
        db.set_fingerprint(canonical["id"], fp)
        # Помечаем остальных как дубли
        for dup in posts[1:]:
            db.set_fingerprint(dup["id"], fp)
            db.mark_as_dup(dup["id"], canonical["id"])
            n_applied += 1

    print(f"[dedupe] ✓ Помечено дублями: {n_applied} постов")
    print(f"[dedupe] ✓ Шум в темах должен снизиться примерно на {n_applied * 100 // max(len(rows), 1)}%")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
