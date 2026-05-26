"""Главный сервис бота @IGDeveloper_bot — long polling + роутинг кнопок.

Архитектура:
  - При старте регистрирует постоянную клавиатуру (3 кнопки) у пользователя
  - В бесконечном цикле слушает getUpdates с timeout=25 (long polling)
  - Маршрутизирует входящие сообщения по тексту кнопки или по состоянию диалога
  - При сбое — пытается переподключиться через 5 сек
  - Состояние диалога хранится в БД (db.bot_state) — переживает рестарты

Меню:
  📊 Сводка недели      → weekly_digest.py логика, шлёт обзор за 7 дней
  🔍 Аналитика          → ставит state=awaiting_query, спрашивает «чем помочь?»
                           следующее текстовое сообщение идёт в analytics.answer_question
  🌡 Температура рынка  → sentiment.py логика, шлёт sentiment-анализ

Запуск:
  python bot_server.py            # в foreground для теста
  через VBS + Task Scheduler at logon — для production
"""

from __future__ import annotations

import sys
import time
import traceback

from anthropic import Anthropic

import analytics
import bot
import config
import sentiment
import weekly_digest
from db import DB

POLL_TIMEOUT = 25  # секунд, long polling
ERROR_BACKOFF = 5  # пауза при ошибке

BTN_WEEKLY = "📊 Сводка недели"
BTN_ANALYTICS = "🔍 Аналитика"
BTN_SENTIMENT = "🌡 Температура рынка"
BTN_MENU = "/menu"

KEYBOARD = [
    [BTN_WEEKLY],
    [BTN_ANALYTICS, BTN_SENTIMENT],
]

WELCOME_TEXT = (
    "<b>Бот-аналитик рынка недвижимости Москвы</b>\n\n"
    "Выбери действие из меню снизу:\n\n"
    f"📊 <b>Сводка недели</b> — структурированный обзор последних 7 дней "
    f"(акции, старты, ставка, коммерция).\n\n"
    f"🔍 <b>Аналитика</b> — напиши название ЖК, БЦ, застройщика или вопрос по рынку, "
    f"я подниму факты из базы за ~2 месяца и сделаю структурированную справку.\n\n"
    f"🌡 <b>Температура рынка</b> — sentiment-анализ за неделю: что разгоняет, "
    f"что сдерживает, что значит для тебя.\n\n"
    "<i>База обновляется автоматически каждое утро в 07:00 из 63 профильных Telegram-каналов.</i>"
)


def handle_weekly(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    """Сводка недели."""
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, "📊 Формирую сводку за неделю... (10-20 сек)")
    bot.send_chat_action(chat_id, "typing")

    try:
        by_topic = weekly_digest.fetch_week_facts(db, days=7)
        total = sum(len(v) for v in by_topic.values())
        if total == 0:
            text = "<b>📊 Итоги недели</b>\n\nЗа 7 дней значимых событий не зафиксировано."
        else:
            ctx = weekly_digest.build_context_for_llm(by_topic)
            from datetime import datetime, timedelta
            today = datetime.now()
            start = today - timedelta(days=7)
            date_range = f"{start.strftime('%d.%m')}—{today.strftime('%d.%m.%Y')}"
            text = weekly_digest.call_llm(client, model, ctx, date_range)

        bot.send_message(chat_id, text, reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(chat_id, f"<b>Ошибка при формировании сводки:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)


def handle_sentiment(chat_id: str, db: DB, client: Anthropic, model: str) -> None:
    """Температура рынка."""
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, "🌡 Анализирую настроение рынка... (10-20 сек)")
    bot.send_chat_action(chat_id, "typing")

    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        cur_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        current = sentiment.fetch_period_summary(db, cur_start.isoformat(), now.isoformat())
        previous = sentiment.fetch_period_summary(db, prev_start.isoformat(), cur_start.isoformat())

        if current.startswith("Нет фактов"):
            text = "<b>🌡 Температура рынка</b>\n\nНедостаточно данных для анализа."
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
        bot.send_message(chat_id, f"<b>Ошибка sentiment-анализа:</b>\n<code>{bot.html_escape(str(exc))}</code>", reply_keyboard=KEYBOARD)


def handle_analytics_request(chat_id: str, db: DB) -> None:
    """Кнопка Аналитика → переход в состояние ожидания вопроса."""
    db.set_bot_state(chat_id, "awaiting_query")
    bot.send_message(
        chat_id,
        "🔍 <b>Чем помочь?</b>\n\n"
        "Напиши название ЖК / БЦ / застройщика или сформулируй вопрос про рынок.\n\n"
        "<i>Примеры:</i>\n"
        "• <code>Republic</code>\n"
        "• <code>iLove</code>\n"
        "• <code>MR Group</code>\n"
        "• <code>что нового по ставке ЦБ?</code>\n"
        "• <code>какие сейчас акции в бизнес-классе</code>\n\n"
        "Чтобы отменить — нажми любую кнопку из меню.",
    )


def handle_query_answer(chat_id: str, query: str, db: DB, client: Anthropic, model: str) -> None:
    """Обработка свободного запроса в режиме Аналитики."""
    bot.send_chat_action(chat_id, "typing")
    bot.send_message(chat_id, f"🔎 Ищу по запросу: <i>{bot.html_escape(query)}</i>...")
    bot.send_chat_action(chat_id, "typing")

    try:
        answer = analytics.answer_question(db, client, model, query)
        bot.send_message(chat_id, answer, reply_keyboard=KEYBOARD)
    except Exception as exc:
        bot.send_message(
            chat_id,
            f"<b>Ошибка при обработке запроса:</b>\n<code>{bot.html_escape(str(exc))}</code>",
            reply_keyboard=KEYBOARD,
        )

    db.set_bot_state(chat_id, "idle")


def handle_start(chat_id: str, db: DB) -> None:
    """Команда /start или /menu — приветствие + клавиатура."""
    db.set_bot_state(chat_id, "idle")
    bot.send_message(chat_id, WELCOME_TEXT, reply_keyboard=KEYBOARD)


def handle_unknown(chat_id: str, text: str, db: DB) -> None:
    """Сообщение в состоянии idle, не совпавшее с кнопками."""
    bot.send_message(
        chat_id,
        "Не понял запроса. Выбери действие из меню или нажми «🔍 Аналитика» чтобы задать вопрос.",
        reply_keyboard=KEYBOARD,
    )


def process_update(update: dict, db: DB, client: Anthropic, model: str, allowed_chat_id: str) -> None:
    """Обрабатывает один update от Telegram."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()

    # Простой allow-list: только Иван может пользоваться ботом
    if chat_id != str(allowed_chat_id):
        print(f"[bot] Игнорирую сообщение от чужого chat_id={chat_id}")
        return

    if not text:
        return

    print(f"[bot] {chat_id} → {text[:80]}")

    # Команды и кнопки
    if text in ("/start", "/menu", BTN_MENU):
        handle_start(chat_id, db)
        return
    if text == BTN_WEEKLY:
        db.set_bot_state(chat_id, "idle")
        handle_weekly(chat_id, db, client, model)
        return
    if text == BTN_SENTIMENT:
        db.set_bot_state(chat_id, "idle")
        handle_sentiment(chat_id, db, client, model)
        return
    if text == BTN_ANALYTICS:
        handle_analytics_request(chat_id, db)
        return

    # Свободный текст — проверяем состояние
    state, _payload = db.get_bot_state(chat_id)
    if state == "awaiting_query":
        handle_query_answer(chat_id, text, db, client, model)
    else:
        handle_unknown(chat_id, text, db)


def main() -> int:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))

    me = bot.get_me()
    if not me.get("ok"):
        print("[bot] Не могу обратиться к Bot API. Проверь TELEGRAM_BOT_TOKEN")
        return 2
    print(f"[bot] Запущен как @{me['result']['username']}, слушаю чат {chat_id}")

    db = DB(config.DB_PATH)
    offset = db.get_bot_offset()
    print(f"[bot] Стартовый offset: {offset}")

    # Один раз шлём в чат welcome — чтобы пользователь сразу увидел клавиатуру
    try:
        bot.send_message(chat_id, "🤖 <b>Бот запущен и готов к работе.</b>\n\nИспользуй меню снизу.", reply_keyboard=KEYBOARD)
    except Exception as exc:
        print(f"[bot] Не удалось отправить welcome: {exc}")

    while True:
        try:
            updates = bot.get_updates(offset=offset + 1, timeout=POLL_TIMEOUT)
            for upd in updates:
                offset = max(offset, upd["update_id"])
                try:
                    process_update(upd, db, client, model, chat_id)
                except Exception:
                    print(f"[bot] Ошибка обработки update {upd.get('update_id')}:")
                    traceback.print_exc()
                db.set_bot_offset(offset)
        except KeyboardInterrupt:
            print("\n[bot] Остановка по Ctrl+C")
            break
        except Exception:
            print("[bot] Ошибка в основном цикле:")
            traceback.print_exc()
            time.sleep(ERROR_BACKOFF)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
