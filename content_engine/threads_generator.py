"""Генератор постов для Threads.

Один Claude-вызов через tool_use с промптом threads-expert.
Ротация формата/ЦА/CTA в Python (без перегруза цепочкой агентов — пост 3-6 строк).
Программный санитайзер проверяет жёсткие правила формата.

Использование:
    python threads_generator.py            # генерит и печатает (не отправляет)
    python threads_generator.py --send     # генерит и шлёт в бот через dispatcher
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SCRIPTS = PROJECT_ROOT / "scripts"
AGENTS = HERE / "agents"

sys.path.insert(0, str(SCRIPTS))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import config  # noqa: E402

ENV_PATH = SCRIPTS / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import anthropic  # noqa: E402
from db import DB  # noqa: E402

MODEL = os.environ.get("CONTENT_MODEL", "claude-sonnet-4-6")

# 6 форматов: веса для рандомного выбора с предпочтением универсальных
FORMAT_WEIGHTS = {1: 25, 2: 15, 3: 12, 4: 15, 5: 13, 6: 20}
FORMAT_NAMES = {
    1: "Жиза", 2: "Раскол", 3: "Обрыв",
    4: "Непопулярное мнение", 5: "Факап", 6: "Наблюдение",
}
AUDIENCES = ["Предприниматели 30-45", "Топ-менеджеры", "Женщины 30-45", "Все три сегмента"]
AUDIENCE_WEIGHTS = [25, 25, 20, 30]  # универсальное чуть чаще

THREADS_TOOL = {
    "name": "write_thread",
    "description": "Пост для Threads по правилам Ивана Гладышева. Чистый текст для one-tap copy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Готовый пост Threads, 3-6 строк, разделённых \\n\\n. Без хэштегов, без заголовков, без меток формата."},
            "self_check": {"type": "string", "description": "1 фраза: почему этот пост зайдёт под выбранный формат (для лога, не публикуется)."},
        },
        "required": ["text", "self_check"],
    },
}


def _load_system() -> str:
    return (AGENTS / "threads-expert.md").read_text(encoding="utf-8")


def _pick_format(db: DB) -> int:
    """Случайный формат с весами, но исключая последние 2 (чтобы не повторяться)."""
    recent = list(db.conn.execute(
        "SELECT format FROM bot_threads_log ORDER BY id DESC LIMIT 2"
    ))
    recent_set = {r["format"] for r in recent}
    pool = [(f, w) for f, w in FORMAT_WEIGHTS.items() if f not in recent_set]
    if not pool:
        pool = list(FORMAT_WEIGHTS.items())
    formats, weights = zip(*pool)
    return random.choices(formats, weights=weights, k=1)[0]


def _pick_audience(db: DB) -> str:
    recent = db.conn.execute(
        "SELECT audience FROM bot_threads_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last = recent["audience"] if recent else None
    pool = [(a, w) for a, w in zip(AUDIENCES, AUDIENCE_WEIGHTS) if a != last]
    if not pool:
        pool = list(zip(AUDIENCES, AUDIENCE_WEIGHTS))
    auds, weights = zip(*pool)
    return random.choices(auds, weights=weights, k=1)[0]


def _should_add_cta(db: DB) -> bool:
    """CTA каждый 3-4 пост (случайно в этом интервале)."""
    last_cta = db.conn.execute(
        "SELECT COUNT(*) AS n FROM bot_threads_log WHERE id > COALESCE((SELECT MAX(id) FROM bot_threads_log WHERE with_cta=1), 0)"
    ).fetchone()
    n_since_cta = last_cta["n"] if last_cta else 0
    threshold = random.choice([3, 4])
    return n_since_cta >= threshold


def _sanitize(text: str) -> str:
    """Проверка/чистка финального текста: убираем хэштеги, лишние эмодзи, странные маркеры."""
    if not text:
        return text
    t = text.strip()
    # убрать хэштеги
    t = re.sub(r"#\S+", "", t)
    # запрещённое «премиум»
    t = re.sub(r"(?i)премиум[\w-]*", "люкс", t)  # мягкая замена, если просочилось
    # стандартизация переносов: одна пустая строка между строками
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    t = "\n\n".join(lines)
    # удалить ведущие/конечные кавычки/код-блоки если Claude обернул
    t = re.sub(r"^[`'\"]+|[`'\"]+$", "", t).strip()
    return t


def generate_thread(client: anthropic.Anthropic, db: DB) -> dict:
    fmt = _pick_format(db)
    audience = _pick_audience(db)
    with_cta = _should_add_cta(db)
    user_msg = (
        f"Формат: {fmt} ({FORMAT_NAMES[fmt]})\n"
        f"ЦА: {audience}\n"
        f"with_cta: {str(with_cta).lower()}\n\n"
        f"Напиши один пост по правилам формата {fmt} для этой ЦА. "
        f"Только сам текст. 3-6 строк, разделённых \\n\\n."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=600,
        system=_load_system(),
        tools=[THREADS_TOOL], tool_choice={"type": "tool", "name": "write_thread"},
        messages=[{"role": "user", "content": user_msg}],
    )
    text, self_check = "", ""
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use":
            text = b.input.get("text", "")
            self_check = b.input.get("self_check", "")
            break
    text = _sanitize(text)
    return {
        "text": text, "self_check": self_check,
        "format": fmt, "format_name": FORMAT_NAMES[fmt],
        "audience": audience, "with_cta": with_cta,
    }


def save_to_log(db: DB, post: dict) -> int:
    cur = db.conn.execute(
        """INSERT INTO bot_threads_log (sent_at, format, audience, with_cta, text)
           VALUES (?, ?, ?, ?, ?)""",
        (
            __import__("datetime").datetime.utcnow().isoformat(),
            post["format"], post["audience"],
            1 if post["with_cta"] else 0, post["text"],
        ),
    )
    return cur.lastrowid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Не только напечатать, но и отправить в бот")
    parser.add_argument("--dry-run", action="store_true", help="Сгенерить, но не записывать в лог")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("✗ ANTHROPIC_API_KEY не задан"); return 1
    client = anthropic.Anthropic(api_key=api_key)
    db = DB(config.DB_PATH)

    post = generate_thread(client, db)
    print(f"[threads] формат: {post['format']} ({post['format_name']}) · ЦА: {post['audience']} · CTA: {post['with_cta']}")
    print(f"[threads] self-check: {post['self_check']}")
    print("=" * 60)
    print(post["text"])
    print("=" * 60)

    if not args.dry_run:
        post_id = save_to_log(db, post)
        print(f"[threads] ✓ записан в лог (id={post_id})")

    if args.send:
        from threads_dispatcher import send_to_bot
        send_to_bot(post)
        print("[threads] ✓ отправлен в бот")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
