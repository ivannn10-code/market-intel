"""Расписание постов на неделю — для кнопки «📅 Расписание недели».

Показывает 7 постов (Пн-Вс) текущей ISO-недели согласно playbook:
  Пн — Разбор объекта
  Вт — Цифра дня
  Ср — Сравнение / расчёт
  Чт — Голосовое (за кулисами)
  Пт — Методология / Red flags + CTA
  Сб — Опрос
  Вс — Дайджест недели

Для каждого дня — статус (отправлен / запланирован / сегодня) + кнопка
«Перегенерить» (если уже есть драфт) или «Создать сейчас» (если ещё нет).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFTS_DIR = HERE / "drafts"
STATE_DIR = HERE / "state"


WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

RUBRIC_BY_WEEKDAY = {
    0: ("review", "Разбор объекта недели"),
    1: ("number", "Цифра дня"),
    2: ("compare", "Сравнение / расчёт"),
    3: ("voice", "Голосовое — за кулисами"),
    4: ("method", "Методология / Red flags + CTA"),
    5: ("poll", "Опрос недели"),
    6: ("digest", "Дайджест недели"),
}


def get_week_dates(today: dt.date | None = None) -> list[dt.date]:
    """Возвращает 7 дат текущей ISO-недели (Пн-Вс)."""
    today = today or dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    return [monday + dt.timedelta(days=i) for i in range(7)]


def find_draft(date: dt.date, rubric: str) -> Path | None:
    """Ищет файл драфта поста."""
    year, week, _ = date.isocalendar()
    week_dir = DRAFTS_DIR / f"{year}-W{week:02d}"
    if not week_dir.exists():
        return None
    weekday_short = WEEKDAYS_SHORT[date.weekday()]
    pattern = f"{date.isoformat()}-{weekday_short}-{rubric}.md"
    path = week_dir / pattern
    return path if path.exists() else None


def was_sent(date: dt.date) -> bool:
    """Проверяет, был ли пост уже отправлен сегодня."""
    lock = STATE_DIR / f"sent-{date.isoformat()}.lock"
    return lock.exists()


def build_schedule_overview() -> tuple[str, list[dict]]:
    """Возвращает (HTML-текст для отображения, список действий для inline-кнопок).

    Действия: [{"date": "2026-05-27", "rubric": "compare", "status": "today", "has_draft": True}, ...]
    """
    today = dt.date.today()
    dates = get_week_dates(today)

    lines = ["📅 <b>Расписание постов на неделю</b>", ""]
    actions = []

    for d in dates:
        rubric, rubric_name = RUBRIC_BY_WEEKDAY[d.weekday()]
        draft = find_draft(d, rubric)
        sent = was_sent(d)
        is_today = d == today
        is_past = d < today

        if sent:
            status = "✅ отправлен"
        elif is_past and not draft:
            status = "⚪ пропущен"
        elif is_past and draft:
            status = "🟡 драфт есть, но не отправлен"
        elif is_today:
            status = "🔥 сегодня"
        elif draft:
            status = "📝 драфт готов"
        else:
            status = "⏳ запланирован"

        weekday_ru = WEEKDAYS_RU[d.weekday()]
        lines.append(
            f"<b>{weekday_ru} {d.strftime('%d.%m')}</b> — {rubric_name}\n"
            f"  {status}"
        )

        actions.append({
            "date": d.isoformat(),
            "rubric": rubric,
            "rubric_name": rubric_name,
            "weekday_ru": weekday_ru,
            "has_draft": draft is not None,
            "sent": sent,
            "is_today": is_today,
            "is_past": is_past,
        })

    lines.append("")
    lines.append("<i>Нажми на день ниже чтобы создать, перегенерить или посмотреть пост.</i>")

    return "\n".join(lines), actions
