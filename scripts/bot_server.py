"""Главный сервис бота @IGDeveloper_bot — long polling + роутинг кнопок + чат-режим.

Меню (7 кнопок в 4 ряда):
  ┌────────────────────────────────────────┐
  │ 📝 Пост на тему    │ 🔄 Перегенерить   │
  ├────────────────────┼───────────────────┤
  │ 📅 Расписание      │ 💬 Чат с Claude  │
  ├────────────────────┴───────────────────┤
  │ 🔍 Аналитика рынка                     │
  ├────────────────────────────────────────┤
  │ 📊 Сводка недели   │ 🌡 Температура    │
  └────────────────────────────────────────┘

Состояния (db.bot_state):
  idle                  — главное меню, ждём нажатия
  awaiting_query        — нажата «Аналитика», ждём вопрос
  awaiting_topic        — нажата «Пост на тему», ждём тему
  chatting              — в режиме чата с Claude, каждое сообщение → reply_in_chat
"""

from __future__ import annotations

import subprocess
import sys
import time
import traceback
from pathlib import Path

from anthropic import Anthropic

# Делаем доступным content_engine/ для import
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT / "content_engine"))
sys.path.insert(0, str(PROJECT_ROOT / "content_engine" / "visual"))

import analytics
import bot
import config
import sentiment
import weekly_digest
import chat  # content_engine/chat.py
import weekly_schedule  # content_engine/weekly_schedule.py
from db import DB

POLL_TIMEOUT = 25
ERROR_BACKOFF = 5

BTN_POST_TOPIC = "📝 Пост на тему"
BTN_REGEN = "🔄 Перегенерить"
BTN_CAROUSEL = "🎨 Создать карусель"
BTN_SCHEDULE = "📅 Расписание недели"
BTN_CHAT = "💬 Чат с Claude"
BTN_ANALYTICS = "🔍 Аналитика рынка"
BTN_WEEKLY = "📊 Сводка недели"
BTN_SENTIMENT = "🌡 Температура рынка"
BTN_CHAT_EXIT = "✓ Завершить чат"

KEYBOARD = [
    [BTN_POST_TOPIC, BTN_REGEN],
    [BTN_CAROUSEL],
    [BTN_SCHEDULE, BTN_CHAT],
    [BTN_ANALYTICS],
    [BTN_WEEKLY, BTN_SENTIMENT],
]

KEYBOARD_CHAT = [
    [BTN_CHAT_EXIT],
]


WELCOME_TEXT = (
    "<b>🤖 Бот @IGDeveloper_bot — твой контент-движок и аналитик рынка</b>\n\n"
    "<b>📝 Пост на тему</b> — напиши тему, бот напишет пост\n"
    "<b>🔄 Перегенерить</b> — переписать последний пост другим вариантом\n"
    "<b>📅 Расписание недели</b> — посты на каждый день\n"
    "<b>💬 Чат с Claude</b> — диалог с AI-аналитиком (видит всю фактуру рынка)\n"
    "<b>🔍 Аналитика</b> — справка по конкретному ЖК / застройщику / теме\n"
    "<b>📊 Сводка недели</b> — итоги последних 7 дней\n"
    "<b>🌡 Температура рынка</b> — sentiment-анализ\n\n"
    "<i>Каждое утро в 08:00 МСК — автоматический пост по контент-плану.</i>"
)


CONTENT_ENGINE_DIR = PROJECT_ROOT / "content_engine"
VENV_PY = PROJECT_ROOT / "venv" / "bin" / "python"


# ============================================================================
# Handlers — кнопки главного меню
# ============================================================================

def handle_start(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, WELCOME_TEXT, reply_keyboard=KEYBOARD)


def handle_weekly_digest(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, "📊 Формирую сводку за неделю... (10-20 сек)")
    bot.send_chat_action(chat_id, "typing")
    try:
        by_topic = weekly_digest.fetch_week_facts(db, days=7)
        total = sum(len(v) for v in by_topic.values())
        if total == 0:
            text = "<b>📊 Итоги недели</b>\n\nЗа 7 дней значимых событий не зафиксировано."
        else:
            from datetime import datetime, timedelta
            today = datetime.now()
            start = today - timedelta(days=7)
            date_range = f"{start.strftime('%d.%m')}—{today.strftime('%d.%m.%Y')}"
            ctx = weekly_digest.build_context_for_llm(by_topic)
            text = weekly_digest.call_llm(client, model, ctx, date_range)
        bot.send_message(chat_id, text, reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)


def handle_sentiment(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, "🌡 Анализирую температуру рынка... (10-20 сек)")
    bot.send_chat_action(chat_id, "typing")
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        cur_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        current = sentiment.fetch_period_summary(db, cur_start.isoformat(), now.isoformat())
        previous = sentiment.fetch_period_summary(db, prev_start.isoformat(), cur_start.isoformat())
        if current.startswith("Нет фактов"):
            text = "<b>🌡 Температура рынка</b>\n\nНедостаточно данных."
        else:
            period_label = f"{cur_start.strftime('%d.%m')}—{now.strftime('%d.%m.%Y')}"
            user_msg = (
                f"Период анализа: {period_label} (7 дней)\n\n"
                f"=== ТЕКУЩИЙ ПЕРИОД ===\n{current}\n\n"
                f"=== ПРЕДЫДУЩИЙ ПЕРИОД ===\n{previous}\n\n"
                f"Сформируй анализ температуры рынка."
            )
            resp = client.messages.create(
                model=model, max_tokens=3000,
                system=sentiment.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        bot.send_message(chat_id, text, reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка sentiment:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)


def handle_analytics_request(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "awaiting_query")
    bot.send_message(
        chat_id,
        "🔍 <b>Чем помочь?</b>\n\n"
        "Напиши название ЖК / БЦ / застройщика или сформулируй вопрос про рынок.\n\n"
        "<i>Примеры:</i>\n"
        "• <code>Republic</code>\n"
        "• <code>MR Group</code>\n"
        "• <code>что нового по ставке ЦБ?</code>\n\n"
        "Чтобы отменить — нажми любую кнопку меню.",
    )


def handle_query_answer(chat_id: str, query: str, db: DB, client: Anthropic, model: str) -> None:
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, f"🔎 Ищу: <i>{bot.html_escape(query)}</i>...")
    bot.send_chat_action(chat_id, "typing")
    try:
        answer = analytics.answer_question(db, client, model, query)
        bot.send_message(chat_id, answer, reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)
    db.set_bot_state(chat_id, "idle")


# === Пост на тему ===

def handle_post_topic_request(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "awaiting_topic")
    bot.send_message(
        chat_id,
        "📝 <b>На какую тему написать пост?</b>\n\n"
        "Напиши тему свободным текстом — бот возьмёт свежую фактуру с рынка и напишет пост в твоём tone of voice.\n\n"
        "<i>Примеры:</i>\n"
        "• <code>Изменения по эскроу в мае</code>\n"
        "• <code>Стартует ли сейчас покупка для жизни в бизнес-классе</code>\n"
        "• <code>Сравни ЖК Republic и Hide</code>\n\n"
        "Отмена — любая кнопка меню.",
    )


def handle_post_topic_answer(chat_id: str, topic: str, db: DB) -> None:
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, f"📝 Пишу пост на тему: <i>{bot.html_escape(topic)}</i>...\nЗайметё 20-40 секунд.")
    bot.send_chat_action(chat_id, "typing")

    try:
        import datetime as dt
        today = dt.date.today().isoformat()
        # Используем рубрику "method" — она оптимальна под произвольную тему
        result = subprocess.run(
            [
                str(VENV_PY), "-u", str(CONTENT_ENGINE_DIR / "daily_post_generator.py"),
                "--date", today,
                "--rubric", "method",
                "--topic-hint", topic,
            ],
            capture_output=True, text=True, timeout=120,
            cwd=str(CONTENT_ENGINE_DIR),
            env={**__import__('os').environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != 0:
            bot.send_message(chat_id, f"<b>Генератор вернул ошибку:</b>\n<code>{bot.html_escape(result.stderr[:1500])}</code>", reply_keyboard=KEYBOARD)
            db.set_bot_state(chat_id, "idle")
            return

        # Парсим путь к файлу из stdout
        post_path = _extract_post_path(result.stdout)
        if post_path and post_path.exists():
            db.save_last_post(chat_id, str(post_path), "method", topic)
            _send_draft(chat_id, post_path)
        else:
            bot.send_message(chat_id, f"<b>Не нашёл файл драфта.</b>\n<code>{result.stdout[-800:]}</code>", reply_keyboard=KEYBOARD)
    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "<b>Таймаут генерации (120с).</b> Попробуй снова.", reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)

    db.set_bot_state(chat_id, "idle")


def _extract_post_path(stdout: str) -> Path | None:
    """Достаёт путь к .md файлу драфта из вывода генератора."""
    import re
    # Generator пишет что-то типа "[gen] ✓ saved: drafts/2026-W22/2026-05-27-ср-method.md"
    m = re.search(r"saved:\s*(\S+\.md)", stdout)
    if m:
        candidate = Path(m.group(1))
        if not candidate.is_absolute():
            candidate = CONTENT_ENGINE_DIR / candidate
        return candidate
    # Альтернативно — ищем любой путь к .md
    for line in stdout.splitlines():
        if ".md" in line and "drafts" in line:
            for token in line.split():
                if token.endswith(".md"):
                    p = Path(token)
                    if not p.is_absolute():
                        p = CONTENT_ENGINE_DIR / p
                    if p.exists():
                        return p
    return None


def _send_draft(chat_id: str, draft_path: Path):
    """Шлёт draft .md файл — frontmatter скрывает, тело отправляет в <pre>."""
    content = draft_path.read_text(encoding="utf-8")
    # Срезаем YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content
    else:
        body = content
    # Отправляем тело в <pre>-блоке для one-tap copy
    bot.send_message(chat_id, f"📄 <b>Пост готов</b> — нажми чтобы скопировать:\n\n<pre>{bot.html_escape(body)}</pre>", reply_keyboard=KEYBOARD)


def handle_regenerate(chat_id: str, db: DB) -> None:
    last = db.get_last_post(chat_id)
    if not last:
        bot.send_message(chat_id, "<b>Нечего перегенерировать.</b>\nСначала запроси пост через «📝 Пост на тему» или дождись утренней автогенерации.", reply_keyboard=KEYBOARD)
        return

    rubric = last.get("rubric") or "method"
    topic = last.get("topic") or ""

    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, f"🔄 Перегенерирую (рубрика {rubric}{', тема: ' + bot.html_escape(topic) if topic else ''})...")
    bot.send_chat_action(chat_id, "typing")

    try:
        import datetime as dt
        today = dt.date.today().isoformat()
        # Удаляем старый draft, чтобы новый сгенерился заново
        old_path = Path(last["post_path"])
        if old_path.exists():
            old_path.unlink()

        cmd = [
            str(VENV_PY), "-u", str(CONTENT_ENGINE_DIR / "daily_post_generator.py"),
            "--date", today, "--rubric", rubric,
        ]
        if topic:
            cmd += ["--topic-hint", topic]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(CONTENT_ENGINE_DIR),
            env={**__import__('os').environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != 0:
            bot.send_message(chat_id, f"<b>Ошибка перегенерации:</b>\n<code>{bot.html_escape(result.stderr[:1500])}</code>", reply_keyboard=KEYBOARD)
            return
        post_path = _extract_post_path(result.stdout)
        if post_path and post_path.exists():
            db.save_last_post(chat_id, str(post_path), rubric, topic)
            _send_draft(chat_id, post_path)
        else:
            bot.send_message(chat_id, "<b>Драфт не найден после перегенерации.</b>", reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)


# === Расписание недели ===

def handle_schedule(chat_id: str, db: DB) -> None:
    text, _actions = weekly_schedule.build_schedule_overview()
    bot.send_message(chat_id, text, reply_keyboard=KEYBOARD)


# === Чат с Claude ===

def handle_chat_enter(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "chatting")
    db.clear_chat_history(chat_id)  # начинаем с чистого листа
    bot.send_message(
        chat_id,
        "💬 <b>Чат с Claude активирован</b>\n\n"
        "Я — твой персональный AI-аналитик. Я вижу:\n"
        "• Всю свежую фактуру рынка (последние 7 дней, ~25 топ-фактов)\n"
        "• Бренд-контекст: твою позицию, аватары ЦА, цифры-якори, tone of voice\n"
        "• Историю нашего диалога\n\n"
        "Можешь просить меня что угодно: написать пост, разобрать тему, накидать идей, "
        "ответить на вопрос клиента, сравнить ЖК. Спрашивай.",
        reply_keyboard=KEYBOARD_CHAT,
    )


def handle_chat_message(chat_id: str, user_msg: str, db: DB, client: Anthropic, model: str) -> None:
    bot.send_chat_action(chat_id, "typing")
    try:
        reply = chat.reply_in_chat(db, client, model, chat_id, user_msg)
        bot.send_message(chat_id, reply, reply_keyboard=KEYBOARD_CHAT)
    except Exception as exc:
        bot.send_message(
            chat_id, f"<b>Ошибка чата:</b>\n<code>{bot.html_escape(str(exc))}</code>",
            reply_keyboard=KEYBOARD_CHAT,
        )


def handle_chat_exit(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, "✓ Чат завершён. История сохранена.", reply_keyboard=KEYBOARD)


# === Создать карусель ===

def handle_carousel_request(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    """Кнопка «Создать карусель» → Claude предлагает 3 темы → inline-кнопки выбора."""
    import json as _json
    import carousel_builder as cb

    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, "🎨 Подбираю 3 темы из свежих фактов рынка... (10-15 сек)")
    bot.send_chat_action(chat_id, "typing")
    try:
        facts = cb.fetch_recent_facts(db, days=7)
        topics = cb.propose_topics(facts, client, model)
        if not topics or len(topics) < 3:
            bot.send_message(chat_id, "<b>Не удалось подобрать темы.</b> Попробуй ещё раз.", reply_keyboard=KEYBOARD)
            return
        # Сохраняем темы в state payload
        db.set_bot_state(chat_id, "carousel_choice", _json.dumps(topics, ensure_ascii=False))
        # Текст + inline-кнопки
        lines = ["🎨 <b>3 темы для карусели:</b>\n"]
        for i, t in enumerate(topics, 1):
            lines.append(f"<b>{i}. {bot.html_escape(t['title'])}</b>\n<i>{bot.html_escape(t.get('angle',''))}</i>\n")
        lines.append("Выбери тему кнопкой ниже или запроси другие 3.")
        buttons = [
            [{"text": f"1️⃣", "callback_data": "car:0"}, {"text": "2️⃣", "callback_data": "car:1"}, {"text": "3️⃣", "callback_data": "car:2"}],
            [{"text": "🔄 Другие 3 темы", "callback_data": "car:more"}],
        ]
        bot.send_message(chat_id, "\n".join(lines), buttons=buttons)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)
        db.set_bot_state(chat_id, "idle")


def handle_carousel_generate(chat_id: str, topic_idx: int, db: DB, client: Anthropic, model: str) -> None:
    """Генерация выбранной карусели: контент → HTML → PNG → отправка."""
    import json as _json
    from pathlib import Path as _Path
    import carousel_builder as cb

    state, payload = db.get_bot_state(chat_id)
    if state != "carousel_choice" or not payload:
        bot.send_message(chat_id, "Сессия выбора истекла. Нажми «🎨 Создать карусель» заново.", reply_keyboard=KEYBOARD)
        return
    topics = _json.loads(payload)
    if topic_idx >= len(topics):
        bot.send_message(chat_id, "Тема не найдена.", reply_keyboard=KEYBOARD)
        return

    topic = topics[topic_idx]["title"]
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, f"🎨 Генерю карусель: <i>{bot.html_escape(topic)}</i>\nЭто 40-70 секунд (Claude пишет слайды + рендер PNG)...")
    bot.send_chat_action(chat_id, "upload_photo")

    try:
        facts = cb.fetch_recent_facts(db, days=7)
        content = cb.generate_carousel_content(topic, facts, client, model)
        if not content:
            bot.send_message(chat_id, "<b>Claude не вернул структуру карусели.</b> Попробуй снова.", reply_keyboard=KEYBOARD)
            return
        import time as _t
        out_dir = _Path("/opt/apps/market-intel/content_engine/visual/generated") / f"carousel-{int(_t.time())}"
        pngs = cb.build_carousel(content, out_dir)
        if not (2 <= len(pngs) <= 10):
            bot.send_message(chat_id, f"<b>Нестандартное число слайдов: {len(pngs)}</b>", reply_keyboard=KEYBOARD)
            return
        bot.send_chat_action(chat_id, "upload_photo")
        bot.send_media_group(chat_id, pngs, caption=f"🎨 {topic} · {len(pngs)} слайдов")
        # Подпись + хэштеги + первый коммент в <pre> для копирования
        cap = cb.caption_md(content)
        bot.send_message(chat_id, f"📝 <b>Подпись + хэштеги + первый коммент</b> (нажми чтобы скопировать):\n\n<pre>{bot.html_escape(cap)}</pre>", reply_keyboard=KEYBOARD)
    except Exception as exc:
        import traceback as _tb
        bot.send_message(chat_id, f"<b>Ошибка генерации карусели:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)
        print(_tb.format_exc())


# ============================================================================
# Главный роутер
# ============================================================================

def process_update(update: dict, db: DB, client: Anthropic, model: str, allowed_chat_id: str) -> None:
    # callback_query — нажатие inline-кнопки
    cq = update.get("callback_query")
    if cq:
        bot.answer_callback_query(cq["id"])
        data = cq.get("data", "")
        cq_chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        if cq_chat != str(allowed_chat_id):
            return
        if data.startswith("car:"):
            choice = data.split(":", 1)[1]
            if choice == "more":
                handle_carousel_request(cq_chat, db, client, model)
            elif choice.isdigit():
                handle_carousel_generate(cq_chat, int(choice), db, client, model)
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    if chat_id != str(allowed_chat_id):
        print(f"[bot] Игнорирую чужой chat_id={chat_id}")
        return
    if not text:
        return

    print(f"[bot] {chat_id} → {text[:80]}")

    # Команды
    if text in ("/start", "/menu"):
        handle_start(chat_id, db)
        return

    # Кнопки главного меню — сбрасывают state
    if text == BTN_WEEKLY:
        db.set_bot_state(chat_id, "idle")
        handle_weekly_digest(chat_id, db, client, model)
        return
    if text == BTN_SENTIMENT:
        db.set_bot_state(chat_id, "idle")
        handle_sentiment(chat_id, db, client, model)
        return
    if text == BTN_ANALYTICS:
        handle_analytics_request(chat_id, db)
        return
    if text == BTN_POST_TOPIC:
        handle_post_topic_request(chat_id, db)
        return
    if text == BTN_REGEN:
        db.set_bot_state(chat_id, "idle")
        handle_regenerate(chat_id, db)
        return
    if text == BTN_CAROUSEL:
        handle_carousel_request(chat_id, db, client, model)
        return
    if text == BTN_SCHEDULE:
        db.set_bot_state(chat_id, "idle")
        handle_schedule(chat_id, db)
        return
    if text == BTN_CHAT:
        handle_chat_enter(chat_id, db)
        return
    if text == BTN_CHAT_EXIT:
        handle_chat_exit(chat_id, db)
        return

    # Свободный текст — зависит от state
    state, _payload = db.get_bot_state(chat_id)
    if state == "awaiting_query":
        handle_query_answer(chat_id, text, db, client, model)
    elif state == "awaiting_topic":
        handle_post_topic_answer(chat_id, text, db)
    elif state == "chatting":
        handle_chat_message(chat_id, text, db, client, model)
    else:
        bot.send_message(
            chat_id,
            "Не понял. Выбери действие из меню или нажми «💬 Чат с Claude» чтобы общаться свободно.",
            reply_keyboard=KEYBOARD,
        )


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))

    me = bot.get_me()
    if not me.get("ok"):
        print("[bot] Не могу обратиться к Bot API")
        return 2
    print(f"[bot] Запущен как @{me['result']['username']}, слушаю чат {chat_id}")

    db = DB(config.DB_PATH)
    offset = db.get_bot_offset()
    print(f"[bot] Стартовый offset: {offset}")

    try:
        bot.send_message(chat_id, "🤖 <b>Бот перезапущен — 7 кнопок доступны.</b>\n\nНажми /menu для краткой справки.", reply_keyboard=KEYBOARD)
    except Exception as exc:
        print(f"[bot] welcome failed: {exc}")

    while True:
        try:
            updates = bot.get_updates(offset=offset + 1, timeout=POLL_TIMEOUT)
            for upd in updates:
                offset = max(offset, upd["update_id"])
                try:
                    process_update(upd, db, client, model, chat_id)
                except Exception:
                    print(f"[bot] update {upd.get('update_id')} ошибка:")
                    traceback.print_exc()
                db.set_bot_offset(offset)
        except KeyboardInterrupt:
            print("\n[bot] Stop.")
            break
        except Exception:
            print("[bot] Ошибка цикла:")
            traceback.print_exc()
            time.sleep(ERROR_BACKOFF)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
