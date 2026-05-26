"""AI-обработка собранных постов через Claude (structured outputs через tool_use).

Делает:
  1. Берёт необработанные посты из БД (processed=0) батчами
  2. Через Anthropic tool_use Claude возвращает строго валидный JSON (schema-checked)
  3. Группирует по темам и дописывает в .business/market-intel/digest/topics/*.md
  4. Генерирует daily-обзор в digest/daily/YYYY-MM-DD.md
  5. Помечает processed=1 ТОЛЬКО для тех, кто реально обработан (потерянные ждут retry)

Режимы:
    python processor.py                 # обычный — все processed=0
    python processor.py --retry-lost    # сбросить processed=0 для постов без тегов, обработать заново
    python processor.py --batch 10      # размер батча (default 15)

Темы (фиксированный список — расширяется в TOPICS):
  - ipoteka-stavka      — ипотека, рассрочка, ставка ЦБ
  - novostroyki-launch  — старты продаж, новые корпуса
  - akcii-zastroyshchikov — акции, скидки, спец. условия
  - kommerciya-bc       — БЦ класса А, офисы, ритейл
  - makroekonomika      — макро, законы, эскроу, ДДУ, налоги
  - analitika-rynka     — цены, объёмы, динамика
  - other               — всё остальное (не записываем в темы, но в daily — да)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

from anthropic import Anthropic

import config
from db import DB

TOPICS = {
    "ipoteka-stavka": "Ипотека, рассрочка, ставка ЦБ",
    "novostroyki-launch": "Старты продаж и новые корпуса",
    "akcii-zastroyshchikov": "Акции и скидки застройщиков",
    "kommerciya-bc": "Коммерция: БЦ класса А, офисы, ритейл",
    "makroekonomika": "Макро, законы, эскроу, ДДУ, налоги",
    "analitika-rynka": "Аналитика рынка: цены, объёмы, динамика",
}

DEFAULT_BATCH_SIZE = 15

SYSTEM_PROMPT = """Ты — аналитик рынка недвижимости Москвы. Работаешь на риелтора, специализирующегося на новостройках бизнес-класса и коммерческой недвижимости класса А.

Твоя задача — обрабатывать посты из профильных Telegram-каналов и извлекать структурированную информацию через инструмент categorize_posts.

КРИТИЧНО: для каждого входящего поста ОБЯЗАТЕЛЬНО создать ровно один элемент в массиве posts. Не пропускай, не объединяй, не добавляй лишних. Порядок элементов должен ТОЧНО соответствовать порядку входящих постов.

Игнорируй (relevant=false): посты-приветствия, опросы без контента, чисто рекламные посты сторонних услуг, эконом-сегмент без связи с бизнес-классом, регионы кроме Москвы/МО."""


# Schema для tool_use — Anthropic API валидирует ответ Claude на этой схеме
def make_categorize_tool(n_posts: int) -> dict:
    topic_enum = list(TOPICS.keys()) + ["other"]
    return {
        "name": "categorize_posts",
        "description": f"Categorize {n_posts} real-estate posts from Telegram channels. MUST return exactly {n_posts} items in the posts array, in the same order as input.",
        "input_schema": {
            "type": "object",
            "properties": {
                "posts": {
                    "type": "array",
                    "minItems": n_posts,
                    "maxItems": n_posts,
                    "items": {
                        "type": "object",
                        "properties": {
                            "relevant": {
                                "type": "boolean",
                                "description": "true если пост содержит фактуру для риелтора по бизнес-классу или коммерции класса А, false для рекламы/оффтопа/эконома"
                            },
                            "topics": {
                                "type": "array",
                                "items": {"type": "string", "enum": topic_enum},
                                "description": "Одна или несколько тем. Если ни одна не подходит — ['other']."
                            },
                            "zhk": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Названия ЖК упомянутых в посте (без слова 'ЖК')"
                            },
                            "bc": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Названия бизнес-центров упомянутых в посте"
                            },
                            "developers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Названия застройщиков (ПИК, Самолёт, MR Group, Donstroy, Level, Sminex, STONE и т.д.)"
                            },
                            "summary": {
                                "type": "string",
                                "description": "1-2 предложения на русском — ЧТО произошло, с цифрами"
                            },
                            "importance": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 5,
                                "description": "5=крупное событие, 3=обычная новость, 1=малозначимо"
                            },
                            "segment": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["zhilye-business", "zhilye-premium", "zhilye-econom", "kommerciya", "makro", "n/a"]}
                            }
                        },
                        "required": ["relevant", "topics", "summary", "importance"]
                    }
                }
            },
            "required": ["posts"]
        }
    }


def claude_client() -> Anthropic:
    api_key = config.env("ANTHROPIC_API_KEY", required=True)
    return Anthropic(api_key=api_key)


def build_user_message(posts: list[dict]) -> str:
    items = []
    for i, p in enumerate(posts):
        items.append(f"<post idx=\"{i}\" channel=\"{p['channel_title']}\" date=\"{p['date']}\">\n{p['text'][:3000]}\n</post>")
    return (
        f"Обработай эти {len(posts)} постов через инструмент categorize_posts. "
        f"Верни ровно {len(posts)} элементов в массиве posts в том же порядке.\n\n"
        + "\n\n".join(items)
    )


def slugify_zhk(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[«»\"\'`]", "", s)
    s = re.sub(r"[^a-zа-я0-9\- ]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60]


def normalize_name(name: str) -> str:
    """Нормализация имени застройщика/ЖК для сравнения."""
    n = name.lower().strip()
    n = re.sub(r"[«»\"\'`,.]", "", n)
    n = re.sub(r"\s+", " ", n)
    # Убираем префиксы "ЖК ", "ГК ", "Группа "
    n = re.sub(r"^(жк|гк|группа|зк|клубный дом|кд)\s+", "", n)
    return n.strip()


def compute_fingerprint(meta: dict, post_date: str) -> str | None:
    """Семантический отпечаток факта: (отсорт. застройщики, отсорт. ЖК+БЦ, primary topic, день).

    Если из факта нельзя вытащить ни одного объекта (ни ЖК, ни БЦ, ни застройщика) — None.
    Тогда дедуп не применяется (берём как уникальный факт)."""
    devs = sorted(set(normalize_name(d) for d in (meta.get("developers") or []) if d))
    objects = sorted(set(
        normalize_name(z) for z in ((meta.get("zhk") or []) + (meta.get("bc") or [])) if z
    ))
    topics = meta.get("topics") or []
    primary_topic = topics[0] if topics else "other"
    day = post_date[:10]  # YYYY-MM-DD

    # Нужен ХОТЯ БЫ один из: застройщик ИЛИ объект (ЖК/БЦ). Иначе слишком общий ключ.
    if not devs and not objects:
        return None

    return f"{'|'.join(devs)}::{'|'.join(objects)}::{primary_topic}::{day}"


def append_to_topic(topic_slug: str, entry_md: str):
    path = config.DIGEST_DIR / "topics" / f"{topic_slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not path.exists()
    with open(path, "a", encoding="utf-8") as f:
        if header_needed:
            human = TOPICS.get(topic_slug, topic_slug)
            f.write(f"# {human}\n\nНакопительный лог фактов из Telegram-каналов. Новые записи — снизу.\n\n---\n\n")
        f.write(entry_md)


def append_to_zhk(zhk_name: str, entry_md: str):
    slug = slugify_zhk(zhk_name)
    if not slug:
        return
    path = config.DIGEST_DIR / "topics" / "zhk" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not path.exists()
    with open(path, "a", encoding="utf-8") as f:
        if header_needed:
            f.write(f"# ЖК «{zhk_name}»\n\nНакопительный лог упоминаний из Telegram-каналов.\n\n---\n\n")
        f.write(entry_md)


def format_entry(post: dict, meta: dict) -> str:
    src = post.get("channel_username") and f"@{post['channel_username']}" or post["channel_title"]
    url = post.get("url") or ""
    date_short = post["date"][:16].replace("T", " ")
    importance = meta.get("importance", 3)
    star = "⭐" * max(1, min(int(importance), 5))
    devs = ", ".join(meta.get("developers", []) or []) or ""
    devs_md = f" — _{devs}_" if devs else ""

    also_in = post.get("also_in") or []
    also_md = ""
    if also_in:
        also_md = f"\n\n_Также в каналах: {', '.join(also_in)}_"

    return (
        f"### {date_short} · {src}{devs_md} {star}\n\n"
        f"{meta.get('summary', post['text'][:300])}{also_md}\n\n"
        f"[Оригинал поста]({url})\n\n"
        "---\n\n"
    )


def write_daily(date_str: str, entries: list[tuple[dict, dict]]):
    path = config.DIGEST_DIR / "daily" / f"{date_str}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    by_topic: dict[str, list[tuple[dict, dict]]] = {}
    for post, meta in entries:
        topics = meta.get("topics") or ["other"]
        for t in topics:
            by_topic.setdefault(t, []).append((post, meta))

    lines = [f"# Daily · {date_str}\n", f"Релевантных постов: **{len(entries)}**\n"]
    order = list(TOPICS.keys()) + ["other"]
    for t in order:
        items = by_topic.get(t)
        if not items:
            continue
        human = TOPICS.get(t, "Прочее")
        lines.append(f"\n## {human}\n")
        items.sort(key=lambda x: x[1].get("importance", 3), reverse=True)
        for post, meta in items:
            date_short = post["date"][:16].replace("T", " ")
            src = post.get("channel_username") and f"@{post['channel_username']}" or post["channel_title"]
            url = post.get("url") or ""
            star = "⭐" * max(1, min(int(meta.get("importance", 3)), 5))
            lines.append(f"- {star} _{date_short} · {src}_ — {meta.get('summary', '')} [→]({url})")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def call_claude(client: Anthropic, model: str, posts: list[dict], max_retries: int = 2) -> list[dict] | None:
    """Один вызов Claude через tool_use. Возвращает список meta или None при провале."""
    tool = make_categorize_tool(len(posts))
    user_msg = build_user_message(posts)

    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": "categorize_posts"},
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as exc:
            print(f"    ! Anthropic API error (попытка {attempt+1}): {exc}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return None

        # Найти tool_use блок в ответе
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                tool_input = block.input
                items = tool_input.get("posts", [])
                if len(items) == len(posts):
                    return items
                print(f"    ! Размер не сошёлся: {len(items)} ≠ {len(posts)} (попытка {attempt+1})")
                break
        else:
            print(f"    ! Нет tool_use блока в ответе (попытка {attempt+1})")

        if attempt < max_retries:
            time.sleep(1)

    return None


def reset_lost(db: DB) -> int:
    """Сбрасывает processed=0 для постов processed=1 без тегов.

    Релевантные посты при первой обработке получают теги (хотя бы topic).
    Если processed=1 но тегов нет — либо это нерелевантный (Claude его пропустил),
    либо потерянный из-за бага batch processing. В обоих случаях безопасно
    переобработать через tool_use — нерелевантные снова отфильтруются, потерянные попадут в темы.
    """
    cur = db.conn.execute(
        """SELECT p.id FROM posts p
           LEFT JOIN post_tags pt ON pt.post_id = p.id
           WHERE p.processed = 1 AND pt.post_id IS NULL"""
    )
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        db.conn.executemany("UPDATE posts SET processed=0 WHERE id=?", [(i,) for i in ids])
    return len(ids)


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--retry-lost", action="store_true", help="Сбросить processed=0 для постов без тегов и переобработать")
    cli.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help=f"Размер батча (default {DEFAULT_BATCH_SIZE})")
    args = cli.parse_args()

    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    db = DB(config.DB_PATH)
    client = claude_client()

    if args.retry_lost:
        n_reset = reset_lost(db)
        print(f"[processor] Сброшено для повторной обработки: {n_reset} постов без тегов")

    posts = db.unprocessed_posts_deduped(limit=10000)
    if not posts:
        print("[processor] Нет необработанных постов.")
        db.close()
        return 0

    n_unique = len(posts)
    n_dups = sum(len(p["dup_ids"]) - 1 for p in posts)
    print(f"[processor] К обработке: {n_unique} уникальных постов (схлопнуто дубликатов: {n_dups}). Батч {args.batch}")

    # Глобальные счётчики
    all_relevant: list[tuple[dict, dict]] = []
    all_ok: list[int] = []
    all_lost: list[int] = []

    total_batches = (len(posts) + args.batch - 1) // args.batch

    for i in range(0, len(posts), args.batch):
        batch = posts[i:i + args.batch]
        batch_data = [
            {
                "id": p["id"],
                "channel_title": p["channel_title"],
                "channel_username": p["channel_username"],
                "date": p["date"],
                "text": p["text"],
                "url": p["url"],
                "also_in": p.get("also_in", []),
                "dup_ids": p.get("dup_ids", [p["id"]]),
            }
            for p in batch
        ]
        batch_num = i // args.batch + 1
        print(f"  → батч {batch_num}/{total_batches}: {len(batch)} постов")

        meta_list = call_claude(client, model, batch_data)

        if meta_list is None and len(batch) > 1:
            print(f"    ↻ батч не сошёлся, обрабатываю поштучно...")
            meta_list = []
            for single in batch_data:
                single_meta = call_claude(client, model, [single], max_retries=1)
                if single_meta and len(single_meta) == 1:
                    meta_list.append(single_meta[0])
                else:
                    meta_list.append(None)

        if meta_list is None:
            print(f"    ✗ батч потерян целиком")
            for p in batch:
                all_lost.extend(p.get("dup_ids", [p["id"]]))
            continue

        for post, meta in zip(batch_data, meta_list):
            dup_ids = post.get("dup_ids", [post["id"]])
            if meta is None:
                all_lost.extend(dup_ids)
                continue

            all_ok.extend(dup_ids)
            if not meta.get("relevant"):
                continue

            # Сохраняем теги ВСЕГДА (для поиска по developer/zhk/topic)
            for topic in (meta.get("topics") or []):
                if topic in TOPICS:
                    tag_id = db.add_tag("topic", topic)
                    db.link_tag(post["id"], tag_id)

            for zhk in (meta.get("zhk") or []):
                tag_id = db.add_tag("zhk", zhk)
                db.link_tag(post["id"], tag_id)

            for bc in (meta.get("bc") or []):
                tag_id = db.add_tag("bc", bc)
                db.link_tag(post["id"], tag_id)

            for dev in (meta.get("developers") or []):
                tag_id = db.add_tag("developer", dev)
                db.link_tag(post["id"], tag_id)

            for seg in (meta.get("segment") or []):
                tag_id = db.add_tag("segment", seg)
                db.link_tag(post["id"], tag_id)

            imp_val = str(int(meta.get("importance", 3)))
            tag_id = db.add_tag("importance", imp_val)
            db.link_tag(post["id"], tag_id)

            # Семантическая дедупликация: вычисляем fingerprint и ищем canonical
            fp = compute_fingerprint(meta, post["date"])
            if fp:
                db.set_fingerprint(post["id"], fp)
                canonical_id = db.find_canonical_by_fingerprint(fp, post["id"])
                if canonical_id is not None:
                    # Это дубль уже существующего факта — НЕ записываем в темы
                    db.mark_as_dup(post["id"], canonical_id)
                    continue

            # Это canonical факт (либо без fingerprint, либо первый по теме) — пишем в темы
            all_relevant.append((post, meta))
            entry = format_entry(post, meta)
            for topic in (meta.get("topics") or []):
                if topic in TOPICS:
                    append_to_topic(topic, entry)
            for zhk in (meta.get("zhk") or []):
                append_to_zhk(zhk, entry)

    # Daily-файлы (только для постов которые ВПЕРВЫЕ стали релевантными в этом прогоне)
    by_date: dict[str, list[tuple[dict, dict]]] = {}
    for post, meta in all_relevant:
        d = post["date"][:10]
        by_date.setdefault(d, []).append((post, meta))
    # Внимание: для retry-lost daily-файлы будут перезаписаны для затронутых дат.
    # Это нежелательно при retry, поэтому пропускаем daily-обновление при retry.
    if not args.retry_lost:
        for d, items in by_date.items():
            write_daily(d, items)

    # Помечаем processed=1 только для тех, кто реально обработан
    db.mark_processed(all_ok)
    print(f"[processor] ✓ Обработано {len(all_ok)}, релевантных: {len(all_relevant)}, потеряно: {len(all_lost)}")
    if not args.retry_lost:
        print(f"[processor] ✓ Daily-файлов обновлено: {len(by_date)}")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
