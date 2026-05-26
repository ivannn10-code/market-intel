"""Автодетект chat_id после того, как пользователь нажал /start у бота.

Запросит getUpdates, найдёт частный chat с пользователем, сохранит chat_id в .env.

Запуск: python bot_setup.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bot
import config


def find_chat_id() -> int | None:
    updates = bot.get_updates()
    if not updates:
        return None

    # Берём самый свежий апдейт из 'message' / 'my_chat_member' / 'callback_query'
    candidates: list[int] = []
    for upd in updates:
        for key in ("message", "edited_message", "my_chat_member", "callback_query"):
            payload = upd.get(key)
            if not payload:
                continue
            chat = (payload.get("chat") or payload.get("from"))
            if chat and chat.get("type") == "private":
                candidates.append(chat["id"])

    if candidates:
        return candidates[-1]  # самый свежий
    return None


def update_env_var(key: str, value: str) -> bool:
    env_path = config.SCRIPTS_DIR / ".env"
    if not env_path.exists():
        print(f"✗ Нет .env в {env_path}")
        return False

    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{key}={value}", content)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"{key}={value}\n"

    env_path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    me = bot.get_me()
    if not me.get("ok"):
        print("✗ Не удалось обратиться к Telegram Bot API. Проверь TELEGRAM_BOT_TOKEN в .env")
        return 2
    bot_username = me["result"]["username"]
    print(f"Бот: @{bot_username}")

    chat_id = find_chat_id()
    if not chat_id:
        print()
        print(f"✗ Не вижу новых сообщений боту. Действия:")
        print(f"  1. Открой Telegram → найди @{bot_username}")
        print(f"  2. Нажми Start (или отправь /start)")
        print(f"  3. Запусти этот скрипт ещё раз: python bot_setup.py")
        return 1

    print(f"✓ Найден chat_id: {chat_id}")

    if update_env_var("TELEGRAM_BOT_CHAT_ID", str(chat_id)):
        print(f"✓ Сохранено в .env: TELEGRAM_BOT_CHAT_ID={chat_id}")
    else:
        print(f"  Сохрани вручную в .env: TELEGRAM_BOT_CHAT_ID={chat_id}")

    # Сразу шлём приветственное сообщение
    try:
        bot.send_message(chat_id, "✓ <b>Парсер подключён</b>\n\nТеперь сюда будут приходить дайджесты рынка и алерты по важным событиям.")
        print("✓ Приветственное сообщение отправлено в бот")
    except Exception as exc:
        print(f"  ✗ Не удалось отправить приветствие: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
