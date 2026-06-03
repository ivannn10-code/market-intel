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
BTN_COVER = "🖼 Картинка к тексту"
BTN_CHAT_EXIT = "✓ Завершить чат"

# Inline-меню (callback_data m:*) — не занимает экран, прокручивается вместе с сообщением.
MENU_INLINE = [
    [{"text": BTN_CAROUSEL, "callback_data": "m:carousel"}, {"text": BTN_POST_TOPIC, "callback_data": "m:post"}],
    [{"text": BTN_COVER, "callback_data": "m:cover"}, {"text": BTN_REGEN, "callback_data": "m:regen"}],
    [{"text": BTN_SCHEDULE, "callback_data": "m:schedule"}, {"text": BTN_CHAT, "callback_data": "m:chat"}],
    [{"text": BTN_ANALYTICS, "callback_data": "m:analytics"}, {"text": BTN_WEEKLY, "callback_data": "m:weekly"}],
    [{"text": BTN_SENTIMENT, "callback_data": "m:sentiment"}],
]

# В режиме чата под ответами — только выход + быстрый возврат в меню.
CHAT_EXIT_INLINE = [
    [{"text": BTN_CHAT_EXIT, "callback_data": "m:chat_exit"}, {"text": "☰ Меню", "callback_data": "m:menu"}],
]

# Команды для нативной кнопки «Меню» (слева от поля ввода).
BOT_COMMANDS = [
    {"command": "menu", "description": "☰ Открыть меню"},
    {"command": "carousel", "description": "🎨 Создать карусель"},
    {"command": "cover", "description": "🖼 Картинка к тексту"},
    {"command": "post", "description": "📝 Пост на тему"},
    {"command": "schedule", "description": "📅 Расписание недели"},
    {"command": "chat", "description": "💬 Чат с Claude"},
    {"command": "analytics", "description": "🔍 Аналитика рынка"},
    {"command": "weekly", "description": "📊 Сводка недели"},
    {"command": "sentiment", "description": "🌡 Температура рынка"},
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
    bot.send_message(chat_id, WELCOME_TEXT, buttons=MENU_INLINE)


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
        bot.send_message(chat_id, text, buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)


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
        bot.send_message(chat_id, text, buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка sentiment:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)


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
        bot.send_message(chat_id, answer, buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)
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
            bot.send_message(chat_id, f"<b>Генератор вернул ошибку:</b>\n<code>{bot.html_escape(result.stderr[:1500])}</code>", buttons=MENU_INLINE)
            db.set_bot_state(chat_id, "idle")
            return

        # Парсим путь к файлу из stdout
        post_path = _extract_post_path(result.stdout)
        if post_path and post_path.exists():
            db.save_last_post(chat_id, str(post_path), "method", topic)
            _send_draft(chat_id, post_path, db)
        else:
            bot.send_message(chat_id, f"<b>Не нашёл файл драфта.</b>\n<code>{result.stdout[-800:]}</code>", buttons=MENU_INLINE)
    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "<b>Таймаут генерации (120с).</b> Попробуй снова.", buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)

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


def _send_draft(chat_id: str, draft_path: Path, db: "DB | None" = None):
    """Шлёт draft .md файл — frontmatter скрывает, тело отправляет в <pre>."""
    content = draft_path.read_text(encoding="utf-8")
    # Срезаем YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content
    else:
        body = content
    # Сохраняем как «ожидает публикации» + кнопки публикации в канал
    if db is not None:
        import json as _json
        db.set_pending_publish(chat_id, "post", _json.dumps({"body": body}, ensure_ascii=False))
        kb = publish_buttons("post")
    else:
        kb = MENU_INLINE
    bot.send_message(chat_id, "📄 <b>Пост готов</b> — нажми чтобы скопировать:")
    bot.send_pre(chat_id, body, buttons=kb)


def handle_regenerate(chat_id: str, db: DB) -> None:
    last = db.get_last_post(chat_id)
    if not last:
        bot.send_message(chat_id, "<b>Нечего перегенерировать.</b>\nСначала запроси пост через «📝 Пост на тему» или дождись утренней автогенерации.", buttons=MENU_INLINE)
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
            bot.send_message(chat_id, f"<b>Ошибка перегенерации:</b>\n<code>{bot.html_escape(result.stderr[:1500])}</code>", buttons=MENU_INLINE)
            return
        post_path = _extract_post_path(result.stdout)
        if post_path and post_path.exists():
            db.save_last_post(chat_id, str(post_path), rubric, topic)
            _send_draft(chat_id, post_path, db)
        else:
            bot.send_message(chat_id, "<b>Драфт не найден после перегенерации.</b>", buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)


# === Расписание недели ===

def handle_schedule(chat_id: str, db: DB) -> None:
    text, _actions = weekly_schedule.build_schedule_overview()
    bot.send_message(chat_id, text, buttons=MENU_INLINE)


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
        buttons=CHAT_EXIT_INLINE,
    )


def handle_chat_message(chat_id: str, user_msg: str, db: DB, client: Anthropic, model: str) -> None:
    bot.send_chat_action(chat_id, "typing")
    try:
        reply = chat.reply_in_chat(db, client, model, chat_id, user_msg)
        bot.send_message(chat_id, reply, buttons=CHAT_EXIT_INLINE)
    except Exception as exc:
        bot.send_message(
            chat_id, f"<b>Ошибка чата:</b>\n<code>{bot.html_escape(str(exc))}</code>",
            buttons=CHAT_EXIT_INLINE,
        )


def handle_chat_exit(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, "✓ Чат завершён. История сохранена.", buttons=MENU_INLINE)


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
            bot.send_message(chat_id, "<b>Не удалось подобрать темы.</b> Попробуй ещё раз.", buttons=MENU_INLINE)
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
        bot.send_message(chat_id, f"<b>Ошибка:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)
        db.set_bot_state(chat_id, "idle")


def handle_carousel_generate(chat_id: str, topic_idx: int, db: DB, client: Anthropic, model: str) -> None:
    """Генерация выбранной карусели: контент → HTML → PNG → отправка."""
    import json as _json
    from pathlib import Path as _Path
    import carousel_builder as cb

    state, payload = db.get_bot_state(chat_id)
    if state != "carousel_choice" or not payload:
        bot.send_message(chat_id, "Сессия выбора истекла. Нажми «🎨 Создать карусель» заново.", buttons=MENU_INLINE)
        return
    topics = _json.loads(payload)
    if topic_idx >= len(topics):
        bot.send_message(chat_id, "Тема не найдена.", buttons=MENU_INLINE)
        return

    topic = topics[topic_idx]["title"]
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, f"🎨 Генерю карусель: <i>{bot.html_escape(topic)}</i>\nЭто 2.5–3.5 мин: редакция агентов (бриф→факт-чек→слайды→вычитка) → AI-фоны (Gemini) → рендер PNG. Пришлю по готовности.")
    bot.send_chat_action(chat_id, "upload_photo")

    def _progress(msg: str) -> None:
        try:
            bot.send_chat_action(chat_id, "upload_photo")
            bot.send_message(chat_id, msg)
        except Exception:
            pass

    try:
        facts = cb.fetch_recent_facts(db, days=7)
        content = cb.generate_carousel_content(topic, facts, client, model, team=True, progress=_progress)
        if not content:
            bot.send_message(chat_id, "<b>Claude не вернул структуру карусели.</b> Попробуй снова.", buttons=MENU_INLINE)
            return
        import time as _t
        out_dir = _Path("/opt/apps/market-intel/content_engine/visual/generated") / f"carousel-{int(_t.time())}"
        pngs = cb.build_carousel(content, out_dir, ai_bg=True, progress=_progress)
        if not (2 <= len(pngs) <= 10):
            bot.send_message(chat_id, f"<b>Нестандартное число слайдов: {len(pngs)}</b>", buttons=MENU_INLINE)
            return
        bot.send_chat_action(chat_id, "upload_photo")
        bot.send_media_group(chat_id, pngs, caption=f"🎨 {topic} · {len(pngs)} слайдов")
        # Подпись + хэштеги + первый коммент в <pre> для копирования
        cap = cb.caption_md(content)
        # Сохраняем как «ожидает публикации» (PNG + подпись) + кнопки публикации в канал
        db.set_pending_publish(chat_id, "carousel", _json.dumps({
            "pngs": [str(p) for p in pngs],
            "caption": content.get("caption", ""),
            "hashtags": content.get("hashtags", []),
            "first_comment": content.get("first_comment", ""),
            "topic": topic,
        }, ensure_ascii=False))
        bot.send_message(chat_id, "📝 <b>Подпись + хэштеги + первый коммент</b> (нажми чтобы скопировать):")
        bot.send_pre(chat_id, cap, buttons=publish_buttons("carousel"))
    except Exception as exc:
        import traceback as _tb
        bot.send_message(chat_id, f"<b>Ошибка генерации карусели:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)
        print(_tb.format_exc())


# ============================================================================
# Картинка к тексту (обложка в hero-стиле: Claude → заголовок, Gemini → фон)
# ============================================================================

def handle_cover_request(chat_id: str, db: DB) -> None:
    db.set_bot_state(chat_id, "awaiting_cover_text")
    bot.send_message(
        chat_id,
        "🖼 <b>Картинка к тексту</b>\n\nПришли текст (идею / заголовок / тезис) — соберу обложку в фирстиле: "
        "хук-заголовок поверх AI-фона (Gemini), как первый слайд карусели.\n\nОтмена — любая кнопка меню.",
    )


def _cover_progress(chat_id: str):
    def _p(m):
        try:
            bot.send_chat_action(chat_id, "upload_photo")
            bot.send_message(chat_id, m)
        except Exception:
            pass
    return _p


def _make_and_send_cover(chat_id: str, text: str, db: DB, client: Anthropic, model: str) -> None:
    import time as _t, json as _json
    from pathlib import Path as _Path
    import carousel_builder as cb
    try:
        content = cb.generate_cover_content(text, client, model)
        if not content:
            bot.send_message(chat_id, "<b>Не удалось собрать обложку.</b> Попробуй другой текст.", buttons=MENU_INLINE)
            return
        out_dir = _Path("/opt/apps/market-intel/content_engine/visual/generated") / f"cover-{int(_t.time())}"
        png = cb.build_cover(content, out_dir, ai_bg=True, progress=_cover_progress(chat_id))
        bot.send_chat_action(chat_id, "upload_photo")
        bot.send_photo(chat_id, png, caption="🖼 Обложка готова")
        db.set_pending_publish(chat_id, "cover", _json.dumps({"png": str(png), "caption": text.strip()}, ensure_ascii=False))
        bot.send_message(chat_id, "✅ <b>Готово к публикации.</b> Нажми, когда устроит:", buttons=publish_buttons("cover"))
    except Exception as exc:
        import traceback as _tb
        bot.send_message(chat_id, f"<b>Ошибка обложки:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)
        print(_tb.format_exc())


def handle_cover_generate(chat_id: str, text: str, db: DB, client: Anthropic, model: str) -> None:
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, "🖼 Делаю обложку: Claude → заголовок, Gemini → фон, рендер. ~40-70 сек…")
    bot.send_chat_action(chat_id, "upload_photo")
    _make_and_send_cover(chat_id, text, db, client, model)


def handle_cover_regen(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    import json as _json
    pending = db.get_pending_publish(chat_id)
    if not pending or pending.get("kind") != "cover":
        bot.send_message(chat_id, "<b>Нет исходного текста.</b> Нажми «🖼 Картинка к тексту» заново.", buttons=MENU_INLINE)
        return
    text = _json.loads(pending["payload"]).get("caption", "")
    bot.send_message(chat_id, "🔄 Делаю другой вариант обложки…")
    bot.send_chat_action(chat_id, "upload_photo")
    _make_and_send_cover(chat_id, text, db, client, model)


# ============================================================================
# Публикация в канал (1 тап)
# ============================================================================

def publish_buttons(kind: str) -> list[list[dict]]:
    """Кнопки под готовым контентом: опубликовать / другой вариант / меню."""
    return [
        [{"text": "✅ Опубликовать в канал", "callback_data": "pub:go"}],
        [{"text": "🔄 Другой вариант", "callback_data": f"pub:regen_{kind}"},
         {"text": "☰ Меню", "callback_data": "m:menu"}],
    ]


def handle_publish(chat_id: str, db: DB) -> None:
    """Публикует «ожидающий» контент (пост/карусель) в TG-канал."""
    import json as _json
    channel = config.env("TELEGRAM_CHANNEL_ID", "")
    if not channel:
        bot.send_message(chat_id, "<b>Канал не настроен.</b> Добавь TELEGRAM_CHANNEL_ID в .env и перезапусти бота.", buttons=MENU_INLINE)
        return
    pending = db.get_pending_publish(chat_id)
    if not pending:
        bot.send_message(chat_id, "<b>Нечего публиковать.</b> Сначала сгенерируй пост или карусель.", buttons=MENU_INLINE)
        return
    try:
        data = _json.loads(pending["payload"])
        if pending["kind"] == "post":
            bot.send_message(channel, data["body"])
        elif pending["kind"] == "cover":
            png = Path(data.get("png", ""))
            if not png.exists():
                bot.send_message(chat_id, "<b>Файл обложки не найден.</b> Сгенерируй заново.", buttons=MENU_INLINE)
                return
            cap = (data.get("caption", "") or "").strip()
            if cap and len(cap) <= 1024:
                bot.send_photo(channel, png, caption=cap)
            else:
                bot.send_photo(channel, png)
                if cap:
                    bot.send_message(channel, cap)
        elif pending["kind"] == "carousel":
            pngs = [Path(p) for p in data.get("pngs", []) if Path(p).exists()]
            if not pngs:
                bot.send_message(chat_id, "<b>Файлы карусели не найдены</b> (могли быть очищены). Сгенерируй заново.", buttons=MENU_INLINE)
                return
            cap = (data.get("caption", "") or "").strip()
            tags = " ".join(data.get("hashtags", []))
            full = (cap + ("\n\n" + tags if tags else "")).strip()
            if full and len(full) <= 1024:
                bot.send_media_group(channel, pngs, caption=full)
            else:
                bot.send_media_group(channel, pngs)
                if full:
                    bot.send_message(channel, full)
        db.clear_pending_publish(chat_id)
        bot.send_message(chat_id, f"✅ <b>Опубликовано в канал</b> {bot.html_escape(channel)}.", buttons=MENU_INLINE)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка публикации:</b>\n<code>{bot.html_escape(str(exc))}</code>", buttons=MENU_INLINE)


# ============================================================================
# Диспетчер действий меню (общий для inline-кнопок m:* и slash-команд)
# ============================================================================

def _dispatch_menu_action(action: str, chat_id: str, db: DB, client: Anthropic, model: str) -> bool:
    """Выполняет действие меню. Возвращает True если действие распознано."""
    if action in ("menu", "start"):
        handle_start(chat_id, db)
    elif action == "carousel":
        handle_carousel_request(chat_id, db, client, model)
    elif action == "cover":
        handle_cover_request(chat_id, db)
    elif action == "post":
        handle_post_topic_request(chat_id, db)
    elif action == "regen":
        db.set_bot_state(chat_id, "idle")
        handle_regenerate(chat_id, db)
    elif action == "schedule":
        db.set_bot_state(chat_id, "idle")
        handle_schedule(chat_id, db)
    elif action == "chat":
        handle_chat_enter(chat_id, db)
    elif action == "analytics":
        handle_analytics_request(chat_id, db)
    elif action == "weekly":
        db.set_bot_state(chat_id, "idle")
        handle_weekly_digest(chat_id, db, client, model)
    elif action == "sentiment":
        db.set_bot_state(chat_id, "idle")
        handle_sentiment(chat_id, db, client, model)
    elif action == "chat_exit":
        handle_chat_exit(chat_id, db)
    else:
        return False
    return True


# Slash-команды → действия меню (для нативной кнопки «Меню» Telegram)
SLASH_TO_ACTION = {
    "/menu": "menu", "/start": "menu",
    "/carousel": "carousel", "/cover": "cover", "/post": "post", "/regen": "regen",
    "/schedule": "schedule", "/chat": "chat", "/analytics": "analytics",
    "/weekly": "weekly", "/sentiment": "sentiment",
}


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
        elif data.startswith("pub:"):
            action = data.split(":", 1)[1]
            if action == "go":
                handle_publish(cq_chat, db)
            elif action == "regen_post":
                db.set_bot_state(cq_chat, "idle")
                handle_regenerate(cq_chat, db)
            elif action == "regen_carousel":
                handle_carousel_request(cq_chat, db, client, model)
            elif action == "regen_cover":
                handle_cover_regen(cq_chat, db, client, model)
        elif data.startswith("m:"):
            _dispatch_menu_action(data.split(":", 1)[1], cq_chat, db, client, model)
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

    # Slash-команды (нативная кнопка «Меню») → действия
    cmd = text.split()[0].lower() if text.startswith("/") else ""
    if cmd in SLASH_TO_ACTION:
        _dispatch_menu_action(SLASH_TO_ACTION[cmd], chat_id, db, client, model)
        return

    # Текстовые кнопки (обратная совместимость со старой клавиатурой) — сбрасывают state
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
    elif state == "awaiting_cover_text":
        handle_cover_generate(chat_id, text, db, client, model)
    elif state == "chatting":
        handle_chat_message(chat_id, text, db, client, model)
    else:
        bot.send_message(
            chat_id,
            "Не понял. Выбери действие из меню или нажми «💬 Чат с Claude» чтобы общаться свободно.",
            buttons=MENU_INLINE,
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

    # Нативная кнопка «Меню» (слева от поля ввода) + список команд
    bot.set_my_commands(BOT_COMMANDS)
    bot.set_chat_menu_button_commands()

    db = DB(config.DB_PATH)
    offset = db.get_bot_offset()
    print(f"[bot] Стартовый offset: {offset}")

    try:
        # 1) снимаем старую постоянную reply-клавиатуру (остаётся закэшированной на клиенте)
        bot.send_message(chat_id, "🧹 Обновляю меню — убираю старую нижнюю клавиатуру…", remove_keyboard=True)
        # 2) показываем компактное inline-меню
        bot.send_message(
            chat_id,
            "🤖 <b>Бот обновлён — меню теперь компактное.</b>\n\n"
            "Старая нижняя клавиатура убрана — больше не занимает экран.\n"
            "Открыть действия: кнопка <b>☰ Меню</b> слева от поля ввода, команда /menu "
            "или кнопки ниже. Меню также появляется под каждым результатом.",
            buttons=MENU_INLINE,
        )
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
