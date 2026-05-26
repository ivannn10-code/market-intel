"""Аналитика по запросу: пользователь пишет название ЖК или общий вопрос — мы достаём
релевантные посты из БД и прогоняем через Claude для структурированного ответа.

Логика:
  1. Определяем тип запроса:
     - Похоже на название ЖК/БЦ → ищем в tags zhk/bc
     - Похоже на застройщика → ищем в tags developer
     - Общий вопрос → FTS полнотекстовый поиск по ключевым словам
  2. Собираем релевантные посты (canonical only, последние 60 дней)
  3. Отправляем в Claude с правильным system prompt
  4. Возвращаем структурированный ответ в Telegram HTML

Использование как модуль:
  from analytics import answer_question
  text = answer_question(db, client, model, "что думаешь про ЖК Republic")

Запуск из CLI (для теста):
  python analytics.py "ЖК Republic"
"""

from __future__ import annotations

import re
import sys

from anthropic import Anthropic

import config
from db import DB


# Стоп-слова для определения "название это или общий вопрос"
QUESTION_MARKERS = {
    "что", "как", "куда", "когда", "где", "почему", "зачем", "сколько",
    "стоит", "какие", "какой", "какая", "?", "акции", "тренд", "ставка",
    "рынок", "сейчас", "сегодня", "недели", "месяца", "квартал",
}


SYSTEM_PROMPT_OBJECT = """Ты — аналитик премиум-эксперта по недвижимости Москвы (Гладышев Иван — 12 лет рынка, специализация: новостройки бизнес-класса + коммерческая А-класса). Тебе передадут факты по конкретному объекту (ЖК, БЦ или застройщику) из профильных Telegram-каналов.

Сформируй структурированную справку для эксперта-практика. Telegram HTML:

🔎 <b>&lt;Название объекта&gt;</b>

<b>📌 Кратко</b>
2-3 предложения: что это, кто застройщик, в каком статусе, основные параметры.

<b>💰 Цены, метражи, условия</b>
Что есть из фактов — цены, площади, рассрочки, ипотечные программы. Конкретно с цифрами.

<b>🎯 Акции и спецпредложения</b>
Свежие акции, скидки, спец. условия. С датами/дедлайнами если есть.

<b>📍 Локация и формат</b>
Где находится, тип проекта, класс. Если из фактов это не понятно — пропусти секцию.

<b>⚠️ На что обратить внимание</b>
Реальные red flags / нюансы / то что нужно проверить. ТОЛЬКО если есть основания из фактов. Не выдумывай.

<b>🗓 Последние упоминания</b>
2-3 буллета: что писали в каналах за последний месяц.

Правила:
1. ТОЛЬКО факты из переданных данных — не выдумывай ничего
2. Если в данных нет какой-то секции — пропусти её, не заполняй мусором
3. Если данных мало (1-2 поста) — честно скажи "данных в базе пока мало" и дай что есть
4. Не используй markdown — только Telegram HTML <b>, <i>
5. Без приветствий, без воды
"""


SYSTEM_PROMPT_GENERAL = """Ты — аналитик премиум-эксперта по недвижимости Москвы (Гладышев Иван). Тебе передали факты из профильных Telegram-каналов по теме вопроса.

Дай развёрнутый ответ на вопрос пользователя. Telegram HTML:

🔍 <b>&lt;Краткая формулировка темы&gt;</b>

<b>Главное</b>
2-3 предложения — суть ответа.

Далее — структура зависит от вопроса. Возможные блоки (выбирай 2-4 релевантных):

<b>📊 Что говорят данные</b>
Конкретные факты с цифрами.

<b>📅 Хронология</b>
Если в вопросе важна динамика — даты и события.

<b>🏗 Кто из застройщиков активен</b>
Если уместно — кто двигается по этой теме.

<b>⚠️ На что обратить внимание</b>
Риски, нюансы — только из данных.

<b>🎯 Практический вывод</b>
1-2 предложения: что это значит для практики риелтора/клиента.

Правила:
1. Только факты из переданных данных
2. Если данных мало — честно скажи "данных пока мало" и дай что есть
3. Цифры сохраняй точно
4. Telegram HTML, без markdown
"""


def looks_like_object_name(query: str) -> bool:
    """Эвристика: запрос — это название ЖК/БЦ/застройщика или общий вопрос?"""
    q = query.strip().lower()
    if "?" in q:
        return False
    words = re.findall(r"\w+", q)
    # Если короткий и нет вопросительных слов — скорее всего название
    if len(words) <= 4 and not any(w in QUESTION_MARKERS for w in words):
        return True
    # Если содержит вопросительные слова — общий вопрос
    if any(w in QUESTION_MARKERS for w in words):
        return False
    # По умолчанию — общий вопрос (безопаснее)
    return False


def find_object_matches(db: DB, query: str) -> tuple[str, list[dict]]:
    """Ищет ЖК / БЦ / застройщика по запросу.
    Возвращает (тип_сущности, список_постов).
    """
    q = query.strip()
    q_lower = q.lower()

    # 1. Ищем точное совпадение по тегам (zhk, bc, developer)
    for kind in ("zhk", "bc", "developer"):
        cur = db.conn.execute(
            "SELECT value FROM tags WHERE kind = ? AND LOWER(value) = LOWER(?)",
            (kind, q),
        )
        row = cur.fetchone()
        if row:
            posts = _fetch_posts_by_tag(db, kind, row[0])
            return (kind, posts)

    # 2. Fuzzy: LIKE по тегам
    for kind in ("zhk", "bc", "developer"):
        cur = db.conn.execute(
            """SELECT value, COUNT(pt.post_id) as cnt FROM tags t
               LEFT JOIN post_tags pt ON pt.tag_id = t.id
               WHERE t.kind = ? AND LOWER(t.value) LIKE LOWER(?)
               GROUP BY t.id
               ORDER BY cnt DESC LIMIT 1""",
            (kind, f"%{q}%"),
        )
        row = cur.fetchone()
        if row:
            posts = _fetch_posts_by_tag(db, kind, row[0])
            if posts:
                return (kind, posts)

    return ("none", [])


def _fetch_posts_by_tag(db: DB, kind: str, value: str, limit: int = 30) -> list[dict]:
    cur = db.conn.execute(
        """SELECT p.date, p.text, p.url, c.username, c.title AS channel,
                  MAX(CASE WHEN t2.kind='importance' THEN CAST(t2.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t2.kind='developer' THEN t2.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t2.kind='zhk' THEN t2.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t2.kind='bc' THEN t2.value END) AS bc,
                  GROUP_CONCAT(DISTINCT CASE WHEN t2.kind='topic' THEN t2.value END) AS topics
           FROM posts p
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           JOIN channels c ON c.id = p.channel_id
           LEFT JOIN post_tags pt2 ON pt2.post_id = p.id
           LEFT JOIN tags t2 ON t2.id = pt2.tag_id
           WHERE t.kind = ? AND t.value = ? AND p.canonical_id IS NULL
           GROUP BY p.id
           ORDER BY p.date DESC LIMIT ?""",
        (kind, value, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def fts_search(db: DB, query: str, limit: int = 25) -> list[dict]:
    """Полнотекстовый поиск (FTS5) — для общих вопросов."""
    # FTS5 не любит спецсимволы — убираем
    safe_q = re.sub(r"[^\w\s]", " ", query)
    safe_q = " ".join(safe_q.split()[:5])  # максимум 5 ключевых слов
    if not safe_q.strip():
        return []
    cur = db.conn.execute(
        """SELECT p.date, p.text, p.url, c.username, c.title AS channel,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk
           FROM posts p
           JOIN posts_fts f ON f.rowid = p.id
           JOIN channels c ON c.id = p.channel_id
           LEFT JOIN post_tags pt ON pt.post_id = p.id
           LEFT JOIN tags t ON t.id = pt.tag_id
           WHERE posts_fts MATCH ? AND p.canonical_id IS NULL
           GROUP BY p.id
           ORDER BY p.date DESC LIMIT ?""",
        (safe_q, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def format_facts_for_llm(posts: list[dict]) -> str:
    if not posts:
        return "Нет фактов в базе."
    lines = []
    for p in posts:
        devs = (p.get("developers") or "").replace(",", ", ")
        zhk = (p.get("zhk") or "").replace(",", ", ")
        bc = (p.get("bc") or "").replace(",", ", ")
        topics = (p.get("topics") or "").replace(",", ", ")
        entities = " · ".join(filter(None, [devs, zhk, bc])) or ""
        text = " ".join((p.get("text") or "").split())[:600]
        channel = f"@{p['username']}" if p.get("username") else p.get("channel", "?")
        lines.append(f"[{p['date'][:10]}] ({channel}) ⭐{p.get('importance') or 3} {entities} — {text}")
    return "\n\n".join(lines)


def answer_question(db: DB, client: Anthropic, model: str, query: str) -> str:
    """Главная функция модуля. Принимает свободный текстовый запрос Ивана,
    возвращает структурированный ответ для отправки в Telegram."""
    query = (query or "").strip()
    if len(query) < 2:
        return "<b>Слишком короткий запрос.</b>\n\nНапиши название ЖК, БЦ, застройщика или вопрос."

    is_object = looks_like_object_name(query)

    if is_object:
        kind, posts = find_object_matches(db, query)
        if not posts:
            # Падаем на FTS
            posts = fts_search(db, query)
            kind = "fts"

        if not posts:
            return (
                f"<b>🔎 По запросу «{query}» в базе ничего не найдено.</b>\n\n"
                f"Попробуй переформулировать или указать более конкретное название.\n\n"
                f"<i>База содержит только посты из ТГ-каналов за последние ~2 месяца. "
                f"Если объект редко упоминается, фактов может не быть.</i>"
            )

        facts_text = format_facts_for_llm(posts)
        user_msg = (
            f"Запрос пользователя: «{query}»\n\n"
            f"Найдено постов: {len(posts)} (тип сущности: {kind})\n\n"
            f"=== ФАКТЫ ИЗ БАЗЫ ===\n{facts_text}\n\n"
            f"Сформируй структурированную справку по правилам системного промпта."
        )
        system = SYSTEM_PROMPT_OBJECT
    else:
        posts = fts_search(db, query)
        if not posts:
            return (
                f"<b>🔎 По запросу «{query}» релевантных фактов в базе не нашлось.</b>\n\n"
                f"Попробуй с другими ключевыми словами или укажи конкретное название."
            )

        facts_text = format_facts_for_llm(posts)
        user_msg = (
            f"Вопрос пользователя: «{query}»\n\n"
            f"Найдено релевантных постов: {len(posts)}\n\n"
            f"=== ФАКТЫ ИЗ БАЗЫ ===\n{facts_text}\n\n"
            f"Дай развёрнутый ответ по правилам системного промпта."
        )
        system = SYSTEM_PROMPT_GENERAL

    resp = client.messages.create(
        model=model,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(b.text for b in resp.content if hasattr(b, "text"))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python analytics.py \"<запрос>\"")
        return 1
    query = " ".join(sys.argv[1:])
    db = DB(config.DB_PATH)
    client = Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))
    model = config.env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    answer = answer_question(db, client, model, query)
    print(answer)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
