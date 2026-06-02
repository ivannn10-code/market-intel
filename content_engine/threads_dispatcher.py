"""Дispatcher для Threads-постов: отправляет готовый текст в бот.

Запускается из cron 3 раза в день. Зовёт threads_generator → отправляет результат
в @IGDeveloper_bot ОДНИМ сообщением: текст в <pre>-блоке для one-tap copy.
Ничего лишнего — Иван копирует и вставляет в приложение Threads.

Использование:
    python threads_dispatcher.py    # сгенерить и отправить
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SCRIPTS = PROJECT_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENV_PATH = SCRIPTS / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import anthropic  # noqa: E402
import bot  # noqa: E402
import config  # noqa: E402
from db import DB  # noqa: E402
from threads_generator import generate_thread, save_to_log  # noqa: E402


def send_to_bot(post: dict) -> None:
    """Шлёт пост в бот: только текст в <pre> для one-tap copy + 1 служебная строка с форматом/ЦА."""
    chat = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
    cta_mark = " · CTA" if post.get("with_cta") else ""
    header = f"🧵 <b>Threads</b> · {post['format_name']} · {post['audience']}{cta_mark}"
    body = post["text"]
    bot.send_message(chat, header)
    bot.send_message(chat, f"<pre>{bot.html_escape(body)}</pre>")


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("✗ ANTHROPIC_API_KEY не задан"); return 1
    client = anthropic.Anthropic(api_key=api_key)
    db = DB(config.DB_PATH)

    try:
        post = generate_thread(client, db)
        save_to_log(db, post)
        send_to_bot(post)
        print(f"[threads] ✓ доставлен в бот · {post['format_name']} · {post['audience']}")
    except Exception as exc:
        # некритично — лог, но не падать (cron продолжит)
        print(f"[threads] ✗ ошибка: {exc}")
        try:
            chat = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
            bot.send_message(chat, f"⚠️ <b>Threads-генератор упал:</b>\n<code>{bot.html_escape(str(exc))}</code>")
        except Exception:
            pass
        db.close()
        return 2

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
