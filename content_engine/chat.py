"""Диалог с Claude в Telegram-боте.

Логика:
  - Пользователь нажимает «💬 Чат с Claude»
  - Бот переходит в state='chatting'
  - Каждое следующее сообщение пользователя добавляется в историю и шлётся в Claude
  - История хранится в БД (bot_chat_history)
  - Claude отвечает с пониманием:
    1. Контекста бренда Ивана (avatar, objections, brand-guidelines)
    2. Всех свежих фактов рынка (через intel.db)
    3. Контента-плана (playbook)
    4. Прошлых сообщений диалога (history)
  - Пользователь может попросить:
    - «напиши пост на тему X»
    - «перепиши последний пост другим тоном»
    - «сгенерируй картинку для поста»
    - «расскажи про ЖК Y»
    - просто болтать про рынок
  - Выход: команда «/завершить» или кнопка «✓ Завершить чат»

Использование как модуль:
  from chat import reply_in_chat
  text = reply_in_chat(db, client, model, chat_id, user_message)
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SCRIPTS = PROJECT_ROOT / "scripts"
BRAND_DIR = HERE / "brand"

sys.path.insert(0, str(SCRIPTS))

from anthropic import Anthropic

import config
from db import DB


MAX_HISTORY_MESSAGES = 20  # Сколько последних сообщений включаем в контекст


def load_brand_context() -> str:
    """Собирает короткий бренд-контекст из файлов brand/.

    Не загружаем всё подряд — берём ключевые блоки. Иначе токены растут.
    """
    parts = ["=== БРЕНД-КОНТЕКСТ ИВАНА ГЛАДЫШЕВА ==="]

    master = BRAND_DIR / "MASTER-BRAND-FILE.md"
    if master.exists():
        # Берём первые 8000 символов — там самое важное
        content = master.read_text(encoding="utf-8")[:8000]
        parts.append(content)

    return "\n\n".join(parts)


def load_fresh_facts(db: DB, days: int = 7, limit: int = 30) -> str:
    """Свежие топ-факты с рынка за последние N дней — для контекста Claude."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = db.conn.execute(
        """SELECT p.date, p.text, p.url,
                  c.username,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS devs,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='topic' THEN t.value END) AS topics
           FROM posts p
           JOIN channels c ON c.id = p.channel_id
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.canonical_id IS NULL AND p.date >= ?
           GROUP BY p.id
           ORDER BY importance DESC, p.date DESC
           LIMIT ?""",
        (since, limit),
    )
    rows = cur.fetchall()
    if not rows:
        return ""

    lines = [f"=== СВЕЖИЕ ФАКТЫ С РЫНКА (последние {days} дней, топ-{limit}) ==="]
    for r in rows:
        devs = (r["devs"] or "").replace(",", ", ")
        zhk = (r["zhk"] or "").replace(",", ", ")
        topics = (r["topics"] or "").replace(",", ", ")
        entities = " · ".join(filter(None, [devs, zhk])) or "—"
        text = " ".join((r["text"] or "").split())[:300]
        lines.append(
            f"[{r['date'][:10]}] ⭐{r['importance'] or 3} [{topics}] [{entities}] — {text}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT_TEMPLATE = """Ты — личный аналитик и помощник Ивана Гладышева, премиум-эксперта по недвижимости Москвы.

Иван — опытный риелтор (12 лет на рынке, 17.5 млрд закрытых сделок, специализация: новостройки бизнес-класса + коммерция класса А). Сейчас он развивает личный бренд через Telegram-канал, и ты помогаешь ему с контентом, аналитикой, разборами.

ТЫ МОЖЕШЬ:
1. Писать посты на любую тему — в его tone of voice (премиум, спокойный, экспертный, с цифрами, без инфоцыганщины)
2. Делать аналитические разборы рынка / конкретного ЖК / застройщика
3. Рекомендовать темы для контента из свежих новостей
4. Помогать с формулировками, заголовками, хуками
5. Объяснять как использовать факты в постах
6. Обсуждать стратегию контента

КЛЮЧЕВЫЕ ПРИНЦИПЫ:
- Все факты — только из переданных данных (свежие посты с рынка + бренд-контекст). НИКАКИХ выдумок про цифры/ЖК.
- Tone of voice: премиум-эксперт, спокойный, с уважением к деньгам и времени клиента. Никаких «вау!», «ребята!», «срочно!»
- Длина: пиши лаконично, не растекайся. Если нужно длиннее — спрашивай.
- Telegram HTML форматирование (<b>, <i>), не Markdown
- Цифры — точно из источников, с указанием источника при необходимости

{brand}

{facts}

=== ТЕКУЩИЙ ДИАЛОГ ==="""


def reply_in_chat(db: DB, client: Anthropic, model: str, chat_id: str, user_message: str) -> str:
    """Главная функция: получить ответ Claude на сообщение в режиме чата."""
    # 1. Сохраняем сообщение пользователя в историю
    db.add_chat_message(chat_id, "user", user_message)

    # 2. Загружаем историю
    history = db.get_chat_history(chat_id, limit=MAX_HISTORY_MESSAGES)

    # 3. Готовим system prompt с контекстом бренда и свежих фактов
    brand = load_brand_context()
    facts = load_fresh_facts(db, days=7, limit=25)
    system = SYSTEM_PROMPT_TEMPLATE.format(brand=brand, facts=facts)

    # 4. Конвертируем историю в формат Anthropic messages
    messages = [{"role": h["role"], "content": h["content"]} for h in history]

    # 5. Вызов Claude
    resp = client.messages.create(
        model=model,
        max_tokens=3000,
        system=system,
        messages=messages,
    )
    reply = "".join(b.text for b in resp.content if hasattr(b, "text"))

    # 6. Сохраняем ответ в историю
    db.add_chat_message(chat_id, "assistant", reply)

    return reply


def clear_chat(db: DB, chat_id: str):
    db.clear_chat_history(chat_id)
