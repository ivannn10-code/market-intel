"""Редакция агентов: команда ролей совместно создаёт каждую единицу контента.

Модель — РЕДКОЛЛЕГИЯ С КРИТИКОЙ:
  1. marketer       — пишет бриф (цель, сегмент, хук, ключевое сообщение, CTA)
  2. fact_checker   — проверяет факты по FACT-CHECK PROTOCOL (НЕ выдумывает, размечает источники)
  3. copywriter     — пишет черновик по брифу + верифицированным фактам
  4. critics        — спецы площадки + маркетолог критикуют черновик (что усилить/убрать)
  5. copywriter     — переписывает с учётом критики
  6. editor         — финальная вычитка (бренд-voice, бан-слова, анти-AI, маркеры источников)

«Агент» = роль (системный промпт из content_engine/agents/, синхронизирован из .claude/agents)
+ шаг Python-конвейера вызовов Anthropic API. Работает автономно на сервере.

Резильентность: каждый шаг в try/except. При сбое любого шага — graceful degradation
(возвращаем лучший имеющийся вариант), редакция НЕ роняет автогенерацию контента.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
AGENTS_DIR = HERE / "agents"
MODEL = os.environ.get("CONTENT_MODEL", "claude-sonnet-4-6")

# Роль команды → файл системного промпта (синхронизирован из .claude/agents)
ROLE_FILE = {
    "marketer": "brand-strategist",
    "instagram": "smm-strategist",
    "telegram": "telegram-expert",
    "carousel": "carousel-designer",
    "copywriter": "copywriter",
    "fact_checker": "real-estate-expert",
}

# Критики по площадке (плюс маркетолог всегда — следит за стратегией/целью)
CRITICS_BY_PLATFORM = {
    "telegram": ["telegram", "marketer"],
    "instagram": ["instagram", "marketer"],
    "carousel": ["carousel", "instagram", "marketer"],
}

# Короткий «хребет» бренда — добавляется к КАЖДОЙ роли (общий контекст и красные линии).
BRAND_SPINE = """
─────────────────────────────────────────────
ОБЩИЙ КОНТЕКСТ (для всех ролей команды)
Эксперт: Иван Гладышев, недвижимость Москвы, 12 лет, 17,5 млрд ₽ сделок.
Специализация: коммерция класса А (офисы/ритейл в БЦ) + жильё бизнес-класса.
УТП: «Я не продаю объекты — подбираю недвижимость под вашу задачу».
4 сегмента ЦА: покупатели жилья бизнес-класса; инвесторы в жильё; инвесторы в коммерцию; бизнес под свой офис.

КРАСНЫЕ ЛИНИИ (нарушать нельзя):
- Тон премиум-эксперта: спокойно, с цифрами и фактами. Без инфоцыганщины, без «AI-привкуса».
- БАН-СЛОВА: «премиум/элитный/эксклюзив», «успей/только сегодня/осталось N мест», «гарантия доходности»,
  «доверьтесь профессионалу», «индивидуальный подход», «инсайдер», «100% юридически чисто», массовое «рекомендую».
- FACT-CHECK: ноль неверифицированных цифр. Каждая цифра/ставка/дата/ЖК — с маркером источника
  (Verified: @канал+дата / Опыт Ивана / Расчёт / Открытое мнение). LLM-память источником НЕ является.
- НЕ выдумывать цифры. Нет в фактуре — не упоминать. Нет голословной критики конкретных ЖК/застройщиков.
─────────────────────────────────────────────
"""

# Финальный редактор — компактная роль (анти-AI + бренд-гейт), пишется здесь.
EDITOR_SYSTEM = """Ты — финальный редактор премиум-бренда Ивана Гладышева. Твоя задача — выпустить текст так,
чтобы его можно было ОДНИМ ТАПОМ опубликовать в Telegram-канал, без правок.

ОБЯЗАТЕЛЬНЫЕ ПРАВКИ ФОРМАТА (это самое важное):
1. УБРАТЬ любые meta-заголовки/строки служебного характера: «# Пост-разбор · Сегмент N · #рубрика»,
   «# Telegram», «Тип контента: …», «Сегмент: …», #-хэштеги в начале. В канал идёт ТОЛЬКО тело поста.
2. УБРАТЬ markdown-разделители «---» между абзацами — заменить на пустую строку.
3. УБРАТЬ заголовки `#`/`##` — TG их не рендерит. Если нужно акцентировать — **жирным**.
4. УБРАТЬ блок источников в конце («📨 Источники: @канал, дата», «Источники: …»).
5. УБРАТЬ ВСЕ @-mentions (@nedvizha, @mrgroupoffice, @stone_developer, любые) — мы не продвигаем чужие каналы.
   Источник вшит в прозу: «по данным ЦБ РФ», «по информации MR Group», «по моему опыту», «по моим расчётам».
6. УБРАТЬ скобки типа «(@channel, дата)», ссылок-URL в тексте быть не должно.
7. Текст НАЧИНАЕТСЯ С ХУКА (без «Сегодня поговорим», «В этом посте разберём»).

ПРАВКИ СТИЛЯ:
- Убрать «AI-привкус»: канцелярит, водные вводки, симметричные списки ради списков, пафос.
- Бан-слова убрать (премиум/элитный/эксклюзив, успей/только сегодня, гарантия доходности, доверьтесь профессионалу,
  индивидуальный подход, инсайдер, 100% юридически чисто, массовое «рекомендую»).
- Каждая цифра — с маркером источника В ПРОЗЕ (см. пункт 5). Спорный факт без маркера — переформулировать как мнение или убрать.
- Сохрани смысл, структуру и длину. НЕ дописывай новых фактов и цифр.
- Живые формулировки от первого лица, где уместно.

Верни ТОЛЬКО финальный текст поста — готовый к публикации, без комментариев, без оборачивания в кавычки или код-блок.
"""


# Регулярные выражения для программной санитизации (последний рубеж).
_RE_META_HASH = re.compile(r"^\s*#[^\n]*$", re.M)             # любые строки начинающиеся с #
_RE_RULE = re.compile(r"^\s*---+\s*$", re.M)                  # markdown-разделители ---
_RE_SOURCES_BLOCK = re.compile(r"\n+\s*(?:📨|📩|📌)?\s*Источник(?:и)?\s*:.*$", re.S | re.I)
_RE_BRACKET_AT = re.compile(r"\s*\(\s*@[^)]*\)")              # «(@channel, дата)»
_RE_AT_MENTION = re.compile(r"@[A-Za-z][\w_]{2,}")            # @nedvizha, @stone_developer и т.п.
_RE_MULTI_BLANK = re.compile(r"\n{3,}")

def sanitize_post(text: str) -> str:
    """Финальная программная вычистка перед сохранением. Убирает meta-заголовки, ---,
    блок «Источники:», @-mentions медиа-каналов, лишние пустые строки. Идемпотентна."""
    if not text:
        return text
    t = text
    t = _RE_META_HASH.sub("", t)
    t = _RE_RULE.sub("", t)
    t = _RE_SOURCES_BLOCK.sub("", t)
    t = _RE_BRACKET_AT.sub("", t)
    t = _RE_AT_MENTION.sub("", t)
    t = _RE_MULTI_BLANK.sub("\n\n", t)
    return t.strip()

_prompt_cache: dict[str, str] = {}


def _load_role(role: str, max_chars: int | None = None) -> str:
    key = f"{role}:{max_chars}"
    if key in _prompt_cache:
        return _prompt_cache[key]
    fname = ROLE_FILE.get(role)
    text = ""
    if fname:
        path = AGENTS_DIR / f"{fname}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n…[промпт сокращён для экономии токенов]"
    _prompt_cache[key] = text
    return text


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _ask(system: str, user: str, *, client=None, max_tokens: int = 2200,
         tool=None, tool_name=None):
    """Один вызов роли. Если задан tool — structured output (dict), иначе текст."""
    client = client or _client()
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}])
    if tool:
        kwargs["tools"] = [tool]
        kwargs["tool_choice"] = {"type": "tool", "name": tool_name or tool["name"]}
    resp = client.messages.create(**kwargs)
    if tool:
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                return b.input
        return None
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()


# ── Шаги конвейера ───────────────────────────────────────────────────────────

BRIEF_TOOL = {
    "name": "content_brief",
    "description": "Креативный бриф для единицы контента премиум-эксперта по недвижимости.",
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "enum": ["sell", "warm", "educate"], "description": "Цель: продать / прогреть / обучить"},
            "segment": {"type": "string", "description": "Какой из 4 сегментов ЦА (1, при необходимости 2)"},
            "hook_angle": {"type": "string", "description": "Угол хука — почему остановит листание/чтение"},
            "key_message": {"type": "string", "description": "Одно ключевое сообщение, которое должно остаться у читателя"},
            "cta": {"type": "string", "description": "Целевое действие (в директ/коммент/сохранить)"},
            "must_include": {"type": "array", "items": {"type": "string"}, "description": "Что обязательно включить (факты/цифры/мысли)"},
            "avoid": {"type": "array", "items": {"type": "string"}, "description": "Чего избежать в этом конкретном тексте"},
        },
        "required": ["goal", "segment", "hook_angle", "key_message", "cta"],
    },
}


def write_brief(topic: str, facts: str, content_type: str, platform: str, client=None) -> dict | None:
    system = _load_role("marketer") + "\n" + BRAND_SPINE
    user = (
        f"Площадка: {platform}. Тип контента: {content_type}.\n"
        f"Тема/задача: {topic}\n\nСвежие факты рынка:\n{facts[:6000]}\n\n"
        f"Составь короткий креативный бриф для этой единицы контента."
    )
    return _ask(system, user, client=client, max_tokens=900, tool=BRIEF_TOOL)


def verify_facts(facts: str, brief: dict, client=None) -> str:
    system = _load_role("fact_checker", max_chars=9000) + "\n" + BRAND_SPINE
    km = (brief or {}).get("key_message", "")
    user = (
        "Ниже — сырые факты с источниками из мониторинга рынка. Твоя задача как fact-checker:\n"
        "1) Отобрать факты, релевантные ключевому сообщению.\n"
        "2) Для КАЖДОГО факта проставить корректный маркер источника (Verified: @канал+дата / Опыт Ивана / Расчёт / Открытое мнение).\n"
        "3) Явно пометить «НЕ ИСПОЛЬЗОВАТЬ» то, что не подтверждено источником.\n"
        "НИЧЕГО НЕ ВЫДУМЫВАЙ. Работай только с присланными фактами.\n\n"
        f"Ключевое сообщение: {km}\n\nСырые факты:\n{facts[:7000]}\n\n"
        "Верни компактный список проверенных фактов с маркерами (то, что копирайтер может смело использовать)."
    )
    return _ask(system, user, client=client, max_tokens=1500)


def write_draft(brief: dict, verified_facts: str, structure_hint: str, content_type: str,
                platform: str, client=None) -> str:
    system = _load_role("copywriter") + "\n" + BRAND_SPINE
    user = (
        f"Площадка: {platform}. Тип/рубрика: {content_type}.\n\n"
        f"БРИФ от маркетолога:\n{_brief_text(brief)}\n\n"
        f"ПРОВЕРЕННЫЕ ФАКТЫ (используй только их, с маркерами):\n{verified_facts}\n\n"
        f"ТРЕБОВАНИЯ К СТРУКТУРЕ И ФОРМАТУ:\n{structure_hint}\n\n"
        f"Напиши черновик. Только текст, без пояснений."
    )
    return _ask(system, user, client=client, max_tokens=2500)


def critique(role: str, draft: str, brief: dict, content_type: str, platform: str, client=None) -> str:
    cap = 9000 if role == "carousel" else None
    system = _load_role(role, max_chars=cap) + "\n" + BRAND_SPINE
    user = (
        f"Ты — критик в роли «{role}». Площадка: {platform}, тип: {content_type}.\n\n"
        f"БРИФ:\n{_brief_text(brief)}\n\nЧЕРНОВИК:\n{draft}\n\n"
        f"Дай КОРОТКУЮ предметную критику со своей экспертной позиции: 3-5 пунктов, что усилить/убрать/"
        f"переформулировать под твою площадку и цель. Без воды, без переписывания — только правки списком."
    )
    return _ask(system, user, client=client, max_tokens=700)


def revise(draft: str, critiques: list[tuple[str, str]], verified_facts: str, brief: dict,
           structure_hint: str, client=None) -> str:
    system = _load_role("copywriter") + "\n" + BRAND_SPINE
    crit_text = "\n\n".join(f"[{role}]\n{c}" for role, c in critiques if c)
    user = (
        f"Ты — копирайтер. Перепиши свой черновик, учтя критику команды.\n\n"
        f"БРИФ:\n{_brief_text(brief)}\n\nПРОВЕРЕННЫЕ ФАКТЫ:\n{verified_facts}\n\n"
        f"ТРЕБОВАНИЯ К СТРУКТУРЕ:\n{structure_hint}\n\n"
        f"КРИТИКА КОМАНДЫ:\n{crit_text}\n\nИСХОДНЫЙ ЧЕРНОВИК:\n{draft}\n\n"
        f"Верни улучшенную версию. Только текст."
    )
    return _ask(system, user, client=client, max_tokens=2500)


def final_edit(text: str, content_type: str, client=None) -> str:
    user = f"Тип контента: {content_type}.\n\nТекст на финальную вычитку:\n\n{text}"
    return _ask(EDITOR_SYSTEM, user, client=client, max_tokens=2500)


def _brief_text(brief: dict | None) -> str:
    if not brief:
        return "(бриф недоступен — пиши по фактуре и здравому смыслу бренда)"
    parts = [
        f"Цель: {brief.get('goal','')}",
        f"Сегмент: {brief.get('segment','')}",
        f"Хук: {brief.get('hook_angle','')}",
        f"Ключевое сообщение: {brief.get('key_message','')}",
        f"CTA: {brief.get('cta','')}",
    ]
    if brief.get("must_include"):
        parts.append("Обязательно: " + "; ".join(brief["must_include"]))
    if brief.get("avoid"):
        parts.append("Избегать: " + "; ".join(brief["avoid"]))
    return "\n".join(parts)


# ── Оркестратор ──────────────────────────────────────────────────────────────

def produce(*, content_type: str, platform: str, facts: str, structure_hint: str,
            topic: str | None = None, progress=None) -> dict:
    """Прогоняет единицу контента через редколлегию. Возвращает {text, brief, critiques, stages}.
    Каждый шаг защищён: при сбое — деградация, но текст всё равно отдаётся."""
    topic = topic or content_type
    client = _client()
    log = {"stages": [], "brief": None, "critiques": []}

    def step(name):
        log["stages"].append(name)
        if progress:
            progress(name)

    # 1) Бриф
    brief = None
    try:
        step("🧭 Маркетолог пишет бриф…")
        brief = write_brief(topic, facts, content_type, platform, client)
        log["brief"] = brief
    except Exception as e:
        print(f"[team] brief failed: {e}")

    # 2) Факт-чек
    verified = facts
    try:
        step("🔎 Факт-чек источников…")
        verified = verify_facts(facts, brief or {}, client) or facts
    except Exception as e:
        print(f"[team] verify failed: {e}")

    # 3) Черновик
    draft = ""
    try:
        step("✍️ Копирайтер пишет черновик…")
        draft = write_draft(brief or {}, verified, structure_hint, content_type, platform, client)
    except Exception as e:
        print(f"[team] draft failed: {e}")

    if not draft:
        # полная деградация: одиночный вызов копирайтера по структуре
        try:
            draft = _ask(_load_role("copywriter") + "\n" + BRAND_SPINE,
                         f"{structure_hint}\n\nФакты:\n{verified[:6000]}", client=client, max_tokens=2500)
        except Exception as e:
            print(f"[team] fallback draft failed: {e}")
            return {"text": "", "brief": brief, "critiques": [], "stages": log["stages"], "ok": False}

    # Режим стоимости: critique (полный, ~7-8 вызовов) | pipeline (без критики, ~4 вызова)
    mode = os.environ.get("TEAM_MODE", "critique").strip().lower()

    # 4) Критика команды
    critiques: list[tuple[str, str]] = []
    if mode != "pipeline":
        try:
            step("🧑‍⚖️ Команда критикует черновик…")
            for role in CRITICS_BY_PLATFORM.get(platform, ["marketer"]):
                try:
                    c = critique(role, draft, brief or {}, content_type, platform, client)
                    if c:
                        critiques.append((role, c))
                except Exception as e:
                    print(f"[team] critique {role} failed: {e}")
            log["critiques"] = critiques
        except Exception as e:
            print(f"[team] critiques stage failed: {e}")

    # 5) Переписать с учётом критики
    final = draft
    if critiques:
        try:
            step("♻️ Копирайтер переписывает по критике…")
            r = revise(draft, critiques, verified, brief or {}, structure_hint, client)
            if r:
                final = r
        except Exception as e:
            print(f"[team] revise failed: {e}")

    # 6) Финальная вычитка
    try:
        step("✅ Финальный редактор вычитывает…")
        e = final_edit(final, content_type, client)
        if e:
            final = e
    except Exception as ex:
        print(f"[team] final_edit failed: {ex}")

    # 7) Программная санитизация — последний рубеж
    final_clean = sanitize_post(final)
    return {"text": final_clean, "brief": brief, "critiques": critiques,
            "verified_facts": verified, "stages": log["stages"], "ok": bool(final_clean)}
