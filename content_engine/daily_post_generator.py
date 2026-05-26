"""V2-генератор постов TG-канала Ивана Гладышева.

ЛОГИКА:
1. Принимает дату + рубрику (или авто-определяет от дня недели).
2. Загружает свежую фактуру из market-intel (последние 1-3 дня) с фильтром
   по релевантности для рубрики.
3. Зовёт Claude API (Sonnet 4.6 по умолчанию) с промптом из playbook
   и фактическим контекстом.
4. Сохраняет результат в drafts/YYYY-WNN/YYYY-MM-DD-<weekday>-<rubric>.md
   с YAML-frontmatter (формат, который понимает daily_dispatcher.py).
5. Опционально: --send отправляет результат в @IGDeveloper_bot для превью.

ИСПОЛЬЗОВАНИЕ:
    # Сгенерировать на конкретную дату с авто-pick фактуры:
    python daily_post_generator.py --date 2026-06-01 --auto

    # Принудительно задать факт (markdown файл):
    python daily_post_generator.py --date 2026-05-25 --facts-file fact.md

    # Сгенерировать и сразу отправить в бот для превью:
    python daily_post_generator.py --date 2026-06-01 --auto --send
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
# content_engine/ лежит ВНУТРИ market-intel/, scripts/ и digest/ — рядом
PROJECT_ROOT = HERE.parent
SCRIPTS = PROJECT_ROOT / "scripts"
DRAFTS_DIR = HERE / "drafts"
TOPICS_DIR = PROJECT_ROOT / "digest" / "topics"
DAILY_DIR = PROJECT_ROOT / "digest" / "daily"

sys.path.insert(0, str(SCRIPTS))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import config  # noqa: E402

# Загружаем .env переменные
ENV_PATH = SCRIPTS / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


import anthropic  # noqa: E402

# Используем Sonnet 4.6 для качества — экспертный текст под премиум-бренд
MODEL = os.environ.get("CONTENT_MODEL", "claude-sonnet-4-6")

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Простое маппинг "день → основная рубрика" (для случая когда --rubric не задан).
# Двойные дни (thu, sat) имеют ДВЕ рубрики — основная (лот) идёт в 08:00,
# дополнительная (voice/poll) идёт в 08:30. Если генерим без --rubric — берётся первая.
WEEKDAY_TO_RUBRIC = {
    "mon": "review",
    "tue": "number",
    "wed": "compare",
    "thu": "lot_commercial",  # 08:00 (основная). Vоice идёт через явный --rubric voice
    "fri": "method",
    "sat": "lot_residential",  # 08:00 (основная). Poll идёт через явный --rubric poll
    "sun": "digest",
}
WEEKDAY_EXTRA_RUBRICS = {
    "thu": ["voice"],
    "sat": ["poll"],
}

# Параметры рубрик (синхронизированы с playbook.md разделы 3.1-3.7)
RUBRIC_CONFIG = {
    "review": {
        "label": "Разбор объекта недели",
        "slot": "heavy",
        "length_min": 1200,
        "length_max": 2200,
        "image": True,
        "voice": False,
        "cta": False,
    },
    "number": {
        "label": "Цифра дня",
        "slot": "light",
        "length_min": 400,
        "length_max": 700,
        "image": False,
        "voice": False,
        "cta": False,
    },
    "compare": {
        "label": "Сравнение / расчёт на бумаге",
        "slot": "heavy",
        "length_min": 1200,
        "length_max": 1800,
        "image": True,
        "voice": False,
        "cta": False,
    },
    "voice": {
        "label": "За кулисами недели (голосовое)",
        "slot": "light",
        "length_min": 1200,
        "length_max": 1700,
        "image": False,
        "voice": True,
        "cta": False,
    },
    "method": {
        "label": "Методология / Red flags",
        "slot": "heavy",
        "length_min": 1500,
        "length_max": 2200,
        "image": False,
        "voice": False,
        "cta": True,
    },
    "poll": {
        "label": "Опрос недели",
        "slot": "light",
        "length_min": 500,
        "length_max": 800,
        "image": False,
        "voice": False,
        "cta": False,
    },
    "digest": {
        "label": "Дайджест недели",
        "slot": "medium",
        "length_min": 800,
        "length_max": 1200,
        "image": True,
        "voice": False,
        "cta": False,
    },
    "lot_commercial": {
        "label": "Лот недели коммерческий",
        "slot": "heavy",
        "length_min": 1200,
        "length_max": 1800,
        "image": True,        # карусель 4-5 слайдов
        "voice": False,
        "cta": True,           # мягкий личный CTA
        "carousel": True,      # отдельный флаг — рендерим mediaGroup, не одну картинку
    },
    "lot_residential": {
        "label": "Лот недели жилой бизнес-класс",
        "slot": "heavy",
        "length_min": 1200,
        "length_max": 1800,
        "image": True,
        "voice": False,
        "cta": True,
        "carousel": True,
    },
}


# ============================================================================
# Общий префикс — встроенная копия из playbook.md раздел 4
# ============================================================================

COMMON_PREFIX = """Ты — Иван Гладышев, эксперт по недвижимости Москвы (12 лет на рынке, 17,5 млрд ₽ сделок, специализация — коммерческая недвижимость класса А и жильё бизнес-класса).

ТОН: спокойный экспертный. Простой язык, без аббревиатур без расшифровки. Конкретные цифры и объекты, никаких «один интересный лот». Личный взгляд через «я думаю», «по моему опыту», «мне это не нравится потому что».

ЗАПРЕЩЕНО использовать слова:
- «премиум», «элитный», «эксклюзив», «эксклюзивно»
- «успей», «только сегодня», «осталось N мест»
- «гарантия доходности», гарантия в %
- «доверьтесь профессионалу», «индивидуальный подход»
- «инсайдер» в публичной коммуникации
- «100% юридически чисто»
- «рекомендую» (массовое риелторское клише)

ОБЯЗАТЕЛЬНО:
- Каждую цифру помечать источником: либо «📨 Источник: @channel, дата, ссылка» (Verified), либо «по моему опыту» (Опыт Ивана), либо «считаю на цифрах» (Расчёт), либо «я думаю» / «моё мнение» (Открытое мнение)
- Расшифровывать NOI (чистый операционный доход), IRR (внутренняя норма доходности), Cap rate, ДКПБН (договор купли-продажи будущей недвижимости), ДДУ, УК (управляющая компания), ПВ (первоначальный взнос), CPI (индекс потребительских цен) при первом упоминании в посте
- НЕ выдумывать цифры. Если цифры нет в фактуре — не упоминать. Если нужна оценка — явно помечать как «по моим прикидкам» или «считаю на цифрах».
- НЕ голословно критиковать конкретные ЖК или застройщиков. Любой минус — только на верифицируемых данных.

Язык: русский.
Формат: Markdown без заголовков H1/H2 (Telegram их не рендерит). Допустимы **жирный**, обычные эмодзи.
"""


# ============================================================================
# Промпты под каждую рубрику
# ============================================================================

PROMPT_REVIEW = """ЗАДАЧА: написать пост-разбор объекта или сделки коммерческой недвижимости Москвы (рубрика «Разбор объекта недели»).

ФАКТУРА (свежие данные с источниками):
{facts}

СТРУКТУРА ПОСТА (соблюдать жёстко):
1. **Хук** — одна цепляющая фраза с ключевой цифрой или фактом (1 строка, 80–120 знаков). Без вводок «Сегодня поговорим».
2. **Контекст** — что именно произошло, когда, кто стороны, чем особенно (3–4 строки).
3. **Что именно мы видим** или «Что получает покупатель» — список 3–5 пунктов с конкретными цифрами из фактуры.
4. **Кому это интересно / Кому это сигнал** — список 2–4 типов читателей (под кого работает этот разбор).
5. **Кому это НЕ подходит / Кому это не сигнал** — список 1–2 типов.
6. **Что я думаю** — 2–3 строки твоего мнения с маркером «я думаю» / «по моему опыту».
7. **📨 Источник:** — последняя строка со ссылкой на оригинальный пост.

ДЛИНА: {length_min}–{length_max} знаков с пробелами.
СЕГМЕНТ: коммерция-инвест + офис под бизнес.

ВАЖНО:
- НЕ дублируй контент. Если в фактуре несколько разных историй — выбери ОДНУ самую сильную и разбери её глубоко.
- В разделе «Что я думаю» — реальное профессиональное суждение, не общие слова.
- В разделе «Кому НЕ подходит» — обязательно дать честный ответ, не пытаться продать всем."""


PROMPT_NUMBER = """ЗАДАЧА: написать короткий пост с одной свежей метрикой рынка коммерции Москвы и кратким комментарием (рубрика «Цифра дня»).

ФАКТУРА:
{facts}

СТРУКТУРА:
1. Хук с цифрой (1 строка).
2. Что это значит — буквально (1–2 строки).
3. Что я отсюда читаю по рынку (2–3 строки, маркер «я думаю» / «по моему опыту»).
4. «📨 Источник:» с ссылкой.

ДЛИНА: {length_min}–{length_max} знаков."""


PROMPT_COMPARE = """ЗАДАЧА: написать пост со сравнительным расчётом двух альтернатив инвестирования (рубрика «Сравнение / расчёт на бумаге»).

ФАКТУРА (актуальные ставки, цены, аренды):
{facts}

ТЕМА СРАВНЕНИЯ: {topic_hint}

СТРУКТУРА:
1. Хук — типичное возражение клиента в кавычках (1 строка).
2. «Считаю на цифрах:» — короткий контекст (1 строка).
3. «**Вариант 1 — [название]**» + 4–5 строк расчёта с цифрами.
4. «**Вариант 2 — [название]**» + 4–5 строк расчёта.
5. «**Что меняет картину:**» — 1–3 фактора, не видных в лоб.
6. «**Вывод:**» — почему сравнение в лоб неверно (2–3 строки).
7. «📨 Источники:» — ссылки.

ДЛИНА: {length_min}–{length_max} знаков.
КРИТИЧНО: каждый расчёт NOI / IRR — с явной формулой и маркером «расчёт» или «считаю на цифрах»."""


PROMPT_VOICE = """ЗАДАЧА: написать сценарий голосового сообщения для Ивана, который он произнесёт в TG-канал (рубрика «За кулисами недели»).

ТЕМА (или подсказка от Ивана): {topic_hint}

ФАКТУРА (опционально, для привязки к свежей новости):
{facts}

ПРАВИЛА СЦЕНАРИЯ:
- Не «выступление», а разговор с одним человеком.
- Простые предложения, короткие. Никакого канцелярита.
- Без цифр, которые нельзя удержать на слух (никаких «36,2 млрд» — лучше «около 36 миллиардов»).
- Должен звучать как личное наблюдение Ивана, не как пересказ статьи.

СТРУКТУРА:
1. Зачин — что произошло на этой неделе (1 фраза).
2. Конкретное наблюдение / инсайт (4–6 строк).
3. Что значит / почему важно (3–4 строки).
4. Вывод-правило для слушателя (2–3 строки).
5. Финал без морали и без CTA (1 строка).

ДЛИНА СЦЕНАРИЯ: {length_min}–{length_max} знаков (≈ 60–90 секунд устной речи)."""


PROMPT_METHOD = """ЗАДАЧА: написать пост-чек-лист по методологии работы с коммерческой недвижимостью (рубрика «Методология / Red flags»).

ТЕМА: {topic_hint}
КОЛИЧЕСТВО ПУНКТОВ: {n_points}

СТРУКТУРА:
1. Хук с обещанием конкретного количества пунктов (1 строка).
2. Контекст: когда применяется (1–2 строки).
3. N пронумерованных пунктов, каждый — короткий заголовок + 2–3 строки объяснения.
4. «**Что важно понять:**» + 1–2 строки общего вывода.
5. CTA — мягкий, уровень 2 из шаблонов плейбука. Пример: «Если хотите применить этот чек-лист к своему варианту — напишите в личку @IVAN_SUNSIDE. Разберу по пунктам, без обязательств.»

ДЛИНА: {length_min}–{length_max} знаков.
СЕГМЕНТ: все, фокус коммерция.

Все методологические пункты — с маркером «по моему опыту» или «я лично проверяю»."""


PROMPT_POLL = """ЗАДАЧА: написать пост с опросом для квалификации аудитории (рубрика «Опрос недели»).

ТЕМА ОПРОСА: {topic_hint}
КОЛИЧЕСТВО ВАРИАНТОВ: 4–5

СТРУКТУРА:
1. Хук — простая формулировка вопроса (1–2 строки).
2. Контекст: зачем спрашиваем (1–2 строки).
3. Опрос: 📊 + вопрос + 4–5 вариантов через 🔘 (каждый с новой строки).
4. Приглашение прокомментировать (1–2 строки).
5. Финал: «правильного ответа нет, есть правильный ответ под задачу» (1 строка).

ДЛИНА: {length_min}–{length_max} знаков.
В КОНЦЕ выдай отдельный блок «POLL_META» со структурой:
POLL_META:
question: <вопрос>
options:
- <вариант 1>
- <вариант 2>
- ...
anonymous: true"""


PROMPT_DIGEST = """ЗАДАЧА: написать сводку 5–7 ключевых событий рынка коммерции Москвы за неделю (рубрика «Дайджест недели»).

ФАКТУРА (события за последние 7 дней):
{facts}

ПРАВИЛА ОТБОРА:
- Не более 1 события на одного застройщика
- Приоритет — события с цифрами и публичной фактурой (важность 4+)
- Если есть негативное событие (провал торгов, банкротство) — обязательно включить, без приукрашивания
- Каждое событие — со ссылкой на оригинал

СТРУКТУРА:
1. Хук — «N событий, 2 минуты чтения» (1 строка).
2. Пронумерованный список 5–7 событий, каждое:
   - **Короткий жирный заголовок события с цифрой**
   - 1 строка контекста (опционально — маркер «следить» / «важно» / «прошло мимо»)
3. «📨 Источники:» — общая ссылка на ленту market-intel.

ДЛИНА: {length_min}–{length_max} знаков."""


PROMPT_LOT_COMMERCIAL = """ЗАДАЧА: написать пост-«Лот недели коммерческий» — конкретный коммерческий лот, который Иван готов сейчас сопровождать (рубрика 3.8 playbook).

ФАКТУРА (исходный пост застройщика + контекст рынка):
{facts}

КРИТИЧНО ПО ТОНУ:
- Это НЕ продающий пост и НЕ реклама застройщика. Это личное предложение брокера.
- Запрещено: «эксклюзивное предложение», «успей купить», «горячий лот», «лучший лот», «выгодное предложение», «срочно».
- Допустимо: «акция действует до конца месяца» (констатация без давления), «у меня сейчас в работе несколько таких лотов» (без слова «успей»).
- В разделе «Что мне интересно» — реальный профессиональный взгляд: что выделяет этот лот, что не видно из презентации застройщика.

СТРУКТУРА (соблюдать жёстко):
1. **Хук** — одна цепляющая фраза с самой сильной цифрой объекта (1 строка, 80–120 знаков).
2. **Объект** — что это, где (адрес/локация), метраж, класс, дата ввода (2–3 строки).
3. **Цена и условия** — конкретно: вход, рассрочка/ипотека, ПВ, прочие условия (3–4 строки).
4. **Заголовок «Что мне интересно в этом лоте:»** + 3–4 строки личного взгляда с маркером «по моему опыту» / «я думаю».
5. **Заголовок «Кому подходит:»** + 2–3 строки с конкретными сценариями задачи покупателя.
6. **Личный CTA** (обязательно): «Этот лот у меня сейчас в работе. Если по задаче подходит — напишите в личку @IVAN_SUNSIDE, разберём по вашей ситуации, без обязательств.» — можно слегка переформулировать, но смысл и handle сохранить.
7. **Подпись внизу:** `#лот_недели #коммерция_москвы`

ДЛИНА: {length_min}–{length_max} знаков.
СЕГМЕНТ: инвесторы коммерции + бизнесы под собственный офис.

ИСТОЧНИКИ: не вставляй прямых ссылок на каналы конкурентов. Если цифра — открытые данные рынка, упоминай нейтрально («по рыночным данным», «на май 2026»)."""


PROMPT_LOT_RESIDENTIAL = """ЗАДАЧА: написать пост-«Лот недели жилой бизнес-класс» — конкретный жилой лот (новостройка бизнес-класса), который Иван готов сейчас сопровождать (рубрика 3.9 playbook).

ФАКТУРА (исходный пост застройщика + контекст рынка):
{facts}

КРИТИЧНО ПО ТОНУ:
- Это НЕ продающий пост и НЕ реклама застройщика. Личное предложение брокера.
- Запрещено: «семья мечты», «дом мечты», «лучшее место для жизни», «срочно цены растут», «эксклюзивное предложение».
- Допустимо: объективные характеристики локации (транспортная доступность, инфраструктура в радиусе 1 км, что строится рядом).
- В разделе «Что мне интересно» — акценты ОБРАЗА ЖИЗНИ, а не доходности (школа, метро, парк, шум, соседство).

СТРУКТУРА (соблюдать жёстко):
1. **Хук** — одна цепляющая фраза о локации или особенности объекта (1 строка).
2. **Объект** — ЖК, корпус, метраж, планировка, класс, дата ввода (2–3 строки).
3. **Цена и условия** — вход, ПВ, доступные ипотечные программы (3–4 строки).
4. **Заголовок «Что мне интересно в этом лоте:»** + 3–4 строки про образ жизни (не про доходность) с маркером «по моему опыту» / «я думаю».
5. **Заголовок «Кому подходит:»** + 2–3 строки про типы семей/задач: молодая семья, trade-up, нерезидент-релокант, инвест-лот под аренду.
6. **Личный CTA:** «Этот лот у меня сейчас в работе. Если по задаче подходит — напишите в личку @IVAN_SUNSIDE, разберём по вашей ситуации, без обязательств.»
7. **Подпись внизу:** `#лот_недели #жильё_бизнес_класса`

ДЛИНА: {length_min}–{length_max} знаков.
СЕГМЕНТ: покупатели квартир для жизни + инвесторы в жилую недвижимость.

ИСТОЧНИКИ: не вставляй ссылок на каналы конкурентов."""


PROMPTS = {
    "review":          PROMPT_REVIEW,
    "number":          PROMPT_NUMBER,
    "compare":         PROMPT_COMPARE,
    "voice":           PROMPT_VOICE,
    "method":          PROMPT_METHOD,
    "poll":            PROMPT_POLL,
    "digest":          PROMPT_DIGEST,
    "lot_commercial":  PROMPT_LOT_COMMERCIAL,
    "lot_residential": PROMPT_LOT_RESIDENTIAL,
}


# ============================================================================
# Загрузка фактуры
# ============================================================================

def load_recent_daily(days: int = 3) -> str:
    """Собирает последние N daily-digest файлов в один текстовый блок."""
    files = sorted(DAILY_DIR.glob("*.md"), reverse=True)[:days]
    if not files:
        return "(нет свежих daily-файлов)"
    chunks = []
    for f in files:
        chunks.append(f"\n=== {f.stem} ===\n{f.read_text(encoding='utf-8')}")
    return "\n".join(chunks)


def load_topic(topic: str, max_lines: int = 200) -> str:
    """Загружает последние N строк из тематического файла."""
    path = TOPICS_DIR / f"{topic}.md"
    if not path.exists():
        return f"(нет файла topics/{topic}.md)"
    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-max_lines:]
    return "\n".join(tail)


def load_facts_for_rubric(rubric: str) -> str:
    """Возвращает фактуру под рубрику."""
    if rubric in ("review", "compare", "digest"):
        return load_topic("kommerciya-bc", 250) + "\n\n" + load_topic("analitika-rynka", 80)
    if rubric == "number":
        return load_topic("analitika-rynka", 120) + "\n\n" + load_topic("makroekonomika", 80)
    return load_recent_daily(3)


# ============================================================================
# Вызов Claude API
# ============================================================================

def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 2500) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY не задан в .env")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Собираем текст из контент-блоков
    parts = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts).strip()


# ============================================================================
# Сохранение результата с frontmatter
# ============================================================================

def iso_week(date: dt.date) -> tuple[int, int]:
    cal = date.isocalendar()
    return cal.year, cal.week


def post_path(date: dt.date, rubric: str) -> Path:
    year, week = iso_week(date)
    folder = DRAFTS_DIR / f"{year}-W{week:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    weekday = WEEKDAY_CODES[date.weekday()]
    return folder / f"{date.isoformat()}-{weekday}-{rubric}.md"


def save_post(date: dt.date, rubric: str, body: str, image_path: str | None = None, sources: list[str] | None = None) -> Path:
    cfg = RUBRIC_CONFIG[rubric]
    weekday = WEEKDAY_CODES[date.weekday()]
    length = len(body.strip())

    is_carousel = bool(cfg.get("carousel", False))
    fm_lines = [
        "---",
        f"date: {date.isoformat()}",
        f"weekday: {weekday}",
        f"rubric: {rubric}",
        f"slot: {cfg['slot']}",
        f"length: {length}",
        f"image: {image_path if image_path else 'null'}",
        f"carousel: {'true' if is_carousel else 'false'}",
        f"voice: {'true' if cfg['voice'] else 'false'}",
        f"cta: {'true' if cfg['cta'] else 'false'}",
        "fact_check: required",
        "generator: v2_auto",
        f"model: {MODEL}",
    ]
    if sources:
        fm_lines.append("sources:")
        for s in sources:
            fm_lines.append(f'  - "{s}"')
    fm_lines.append("---")
    fm_lines.append("")

    content = "\n".join(fm_lines) + body.strip() + "\n"

    path = post_path(date, rubric)
    path.write_text(content, encoding="utf-8")
    return path


# ============================================================================
# main
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="ISO дата YYYY-MM-DD")
    parser.add_argument("--rubric", help="Принудительно: review/number/compare/voice/method/poll/digest. По умолчанию — от дня недели.")
    parser.add_argument("--facts-file", type=Path, help="Markdown файл с готовой фактурой (вместо авто-pick из market-intel)")
    parser.add_argument("--topic-hint", default="", help="Подсказка по теме (для compare/voice/method/poll)")
    parser.add_argument("--n-points", type=int, default=7, help="Количество пунктов для рубрики method")
    parser.add_argument("--max-tokens", type=int, default=2500)
    parser.add_argument("--image-path", help="Путь к картинке (relative to telegram-daily/), если есть")
    parser.add_argument("--source", action="append", help="Источник для frontmatter (можно несколько раз)")
    parser.add_argument("--dry-run", action="store_true", help="Не сохранять, только напечатать результат")
    args = parser.parse_args()

    try:
        date = dt.date.fromisoformat(args.date)
    except ValueError:
        print(f"✗ Невалидная дата: {args.date}", file=sys.stderr)
        return 1

    weekday = WEEKDAY_CODES[date.weekday()]
    rubric = args.rubric or WEEKDAY_TO_RUBRIC[weekday]
    if rubric not in PROMPTS:
        print(f"✗ Неизвестная рубрика: {rubric}", file=sys.stderr)
        return 1

    cfg = RUBRIC_CONFIG[rubric]
    print(f"[gen] date={date.isoformat()} weekday={weekday} rubric={rubric}")
    print(f"[gen] длина: {cfg['length_min']}–{cfg['length_max']} знаков")
    print(f"[gen] модель: {MODEL}")

    # Фактура
    if args.facts_file:
        facts = args.facts_file.read_text(encoding="utf-8")
        print(f"[gen] facts: из файла {args.facts_file} ({len(facts)} знаков)")
    else:
        facts = load_facts_for_rubric(rubric)
        print(f"[gen] facts: авто из market-intel ({len(facts)} знаков)")

    # Сборка промпта
    prompt_template = PROMPTS[rubric]
    user_prompt = prompt_template.format(
        facts=facts,
        topic_hint=args.topic_hint,
        n_points=args.n_points,
        length_min=cfg["length_min"],
        length_max=cfg["length_max"],
    )

    print(f"[gen] промпт собран ({len(user_prompt)} знаков)")
    print(f"[gen] → зову Claude API ({MODEL})...")

    body = call_claude(COMMON_PREFIX, user_prompt, max_tokens=args.max_tokens)
    print(f"[gen] ✓ получен ответ ({len(body)} знаков)")

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRAFT (dry-run, не сохранён):")
        print("=" * 60)
        print(body)
        return 0

    path = save_post(date, rubric, body, image_path=args.image_path, sources=args.source or [])
    print(f"[gen] ✓ сохранён: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
