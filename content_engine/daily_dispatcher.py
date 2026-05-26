"""Дирижёр ежедневной отправки поста Ивану в @IGDeveloper_bot.

ЛОГИКА:
1. Определить сегодняшнюю дату → ISO неделя → найти файл
   drafts/YYYY-WNN/YYYY-MM-DD-<weekday>-<rubric>.md
2. Если уже отправляли (есть state/sent-YYYY-MM-DD.lock) → выйти OK
3. Парсить frontmatter (image, voice, rubric, cta, poll)
4. Отправить пакет в бот:
   • заголовок-метка
   • картинка (если image указан в frontmatter)
   • текст поста в <pre>-блоке для one-tap copy
   • инструкция голосового (если voice: true)
   • инструкция опроса (если есть poll: в frontmatter)
   • инструкция CTA (если cta: true)
5. Если файла нет → отправить fallback-уведомление Ивану и завершиться с кодом 2.
6. После успешной отправки → создать lock-файл с timestamp.
7. Всё логируется в logs/dispatch-YYYY-MM-DD.log

ЗАПУСК:
    .business/market-intel/venv/Scripts/python.exe \
        .business/marketing/telegram-daily/daily_dispatcher.py

ОПЦИИ:
    --date YYYY-MM-DD     — переопределить «сегодня» (для тестов)
    --force               — игнорировать lock-файл (для повторных отправок)
    --dry-run             — только посчитать, что отправилось бы, без бота
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any

# --- пути -----------------------------------------------------------------

HERE = Path(__file__).resolve().parent  # market-intel/content_engine/
PROJECT_ROOT = HERE.parent  # market-intel/
SCRIPTS = PROJECT_ROOT / "scripts"
DRAFTS_DIR = HERE / "drafts"
STATE_DIR = HERE / "state"
LOGS_DIR = HERE / "logs"

sys.path.insert(0, str(SCRIPTS))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot  # noqa: E402  — market-intel/scripts/bot.py
import config  # noqa: E402

# --- константы ------------------------------------------------------------

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_RU = {
    "mon": "Понедельник", "tue": "Вторник", "wed": "Среда",
    "thu": "Четверг", "fri": "Пятница", "sat": "Суббота", "sun": "Воскресенье",
}
RUBRIC_LABEL = {
    "review":           "🔎 Разбор объекта",
    "number":           "📊 Цифра дня",
    "compare":          "⚖️ Сравнение / расчёт",
    "voice":            "🎤 Голосовое — за кулисами",
    "method":           "📋 Методология / Red flags",
    "poll":             "🗳 Опрос недели",
    "digest":           "📰 Дайджест недели",
    "lot_commercial":   "🏢 Лот недели — коммерческий",
    "lot_residential":  "🏠 Лот недели — жилой бизнес-класс",
}
# Порядок отправки в двойные дни: сначала тяжёлый «лот» (08:00),
# затем лёгкий формат (08:30). Если сегодня несколько файлов — сортируем по этому порядку.
RUBRIC_DELIVERY_ORDER = [
    "review", "lot_commercial", "lot_residential",  # тяжёлые с визуалом — первыми
    "compare", "method", "digest",                  # тяжёлые без карусели
    "number", "voice", "poll",                      # лёгкие
]

# --- логирование ----------------------------------------------------------

def _log_path(today: dt.date) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"dispatch-{today.isoformat()}.log"


def log(today: dt.date, msg: str) -> None:
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with _log_path(today).open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# --- frontmatter parser (минимальный, без PyYAML) -------------------------

FM_OPEN = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Разбирает YAML-подобный frontmatter в начале файла.

    Поддерживает: строки key: value, списки через "- item",
    nested 2-spaces для poll.options. Без полного YAML — нам не нужно.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FM_OPEN:
        return {}, text

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FM_OPEN:
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:]).lstrip("\n")

    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None
    current_dict: dict[str, Any] | None = None

    for raw in fm_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        # Уровень 0 — "key: value" или "key:"
        if not raw.startswith(" ") and not raw.startswith("\t"):
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                data[key] = []
                current_key = key
                current_list = data[key]
                current_dict = None
            else:
                data[key] = _coerce_scalar(value)
                current_key = None
                current_list = None
                current_dict = None
            continue

        stripped = raw.strip()
        # элемент списка
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if current_list is not None:
                current_list.append(_coerce_scalar(item))
            continue

        # nested key для словаря (например poll.question)
        if ":" in stripped and current_key is not None:
            if current_dict is None:
                # Перестраиваем: ключ — словарь, а не список
                data[current_key] = {}
                current_dict = data[current_key]
                current_list = None
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if not v:
                current_dict[k] = []
                current_list = current_dict[k]
            else:
                current_dict[k] = _coerce_scalar(v)

    return data, body


def _coerce_scalar(v: str) -> Any:
    s = v.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.lower() in {"true", "yes"}:
        return True
    if s.lower() in {"false", "no"}:
        return False
    if s.lower() in {"null", "none", "~"}:
        return None
    try:
        if s.isdigit():
            return int(s)
        return float(s)
    except ValueError:
        return s


# --- поиск файла дня ------------------------------------------------------

def iso_week(date: dt.date) -> tuple[int, int]:
    """Возвращает (год_ISO, номер_недели_ISO)."""
    cal = date.isocalendar()
    return cal.year, cal.week


def find_post_file(date: dt.date) -> Path | None:
    """Назад-совместимый поиск ОДНОГО файла на дату. Используется только в логах/fallback."""
    files = find_all_post_files(date)
    return files[0] if files else None


def find_all_post_files(date: dt.date) -> list[Path]:
    """Возвращает ВСЕ файлы на сегодняшнюю дату (для двойных дней).
    Сортирует по RUBRIC_DELIVERY_ORDER: тяжёлые/карусели → лёгкие."""
    year, week = iso_week(date)
    folder = DRAFTS_DIR / f"{year}-W{week:02d}"
    if not folder.exists():
        return []
    weekday = WEEKDAY_CODES[date.weekday()]
    pattern = f"{date.isoformat()}-{weekday}-*.md"
    matches = list(folder.glob(pattern))

    def order_key(path: Path) -> int:
        for i, rubric in enumerate(RUBRIC_DELIVERY_ORDER):
            if f"-{rubric}.md" in path.name or f"-{rubric}-" in path.name:
                return i
        return 999

    return sorted(matches, key=order_key)


# --- lock-файл ------------------------------------------------------------

def lock_path(date: dt.date, rubric: str | None = None) -> Path:
    """Lock-файл per-post (date + rubric). Защита от двойных отправок.
    Если rubric=None — возвращает старый формат (для обратной совместимости)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if rubric:
        return STATE_DIR / f"sent-{date.isoformat()}-{rubric}.lock"
    return STATE_DIR / f"sent-{date.isoformat()}.lock"


def already_sent(date: dt.date, rubric: str | None = None) -> bool:
    """Проверка: уже отправлен ли пост этой рубрики сегодня.
    Также проверяется старый общий lock (для обратной совместимости с W22)."""
    if rubric and lock_path(date, rubric).exists():
        return True
    if rubric is None and lock_path(date).exists():
        return True
    return False


def mark_sent(date: dt.date, rubric: str, info: dict[str, Any]) -> None:
    info_with_ts = {"sent_at": dt.datetime.now().isoformat(timespec="seconds"), **info}
    lock_path(date, rubric).write_text(json.dumps(info_with_ts, ensure_ascii=False, indent=2), encoding="utf-8")


# --- доставка ------------------------------------------------------------

def deliver(date: dt.date, post_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    raw = post_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)

    rubric = meta.get("rubric", "unknown")
    weekday_code = meta.get("weekday", WEEKDAY_CODES[date.weekday()])
    is_voice = bool(meta.get("voice", False))
    is_cta = bool(meta.get("cta", False))
    is_carousel = bool(meta.get("carousel", False))
    cta_level = meta.get("cta_level", 1)
    image_rel = meta.get("image")
    poll = meta.get("poll")

    label = RUBRIC_LABEL.get(rubric, "📝 Пост")
    weekday_ru = WEEKDAY_RU.get(weekday_code, "")
    length = meta.get("length", len(body.strip()))

    summary = {
        "date": date.isoformat(),
        "post_file": str(post_path.relative_to(PROJECT_ROOT)),
        "rubric": rubric,
        "image": image_rel,
        "carousel": is_carousel,
        "voice": is_voice,
        "cta": is_cta,
        "poll": bool(poll),
        "length": length,
        "dry_run": dry_run,
    }

    if dry_run:
        log(date, f"[DRY-RUN] Доставил бы: {json.dumps(summary, ensure_ascii=False)}")
        return summary

    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)

    # 1) заголовок-метка
    header = (
        f"📬 <b>Свежий пост на сегодня</b>\n"
        f"<i>{weekday_ru} · {date.strftime('%d.%m.%Y')}</i>\n\n"
        f"{label} · {length} знаков\n"
        f"Подготовлено: посмотри, при необходимости поправь, опубликуй в канале."
    )
    bot.send_message(chat_id, header)

    # 2) визуал — карусель (mediaGroup) или одна картинка
    if image_rel:
        image_path = (HERE / image_rel).resolve()
        if is_carousel:
            # image_rel указывает на ПАПКУ с PNG-слайдами (slide-01.png, slide-02.png, …)
            if image_path.exists() and image_path.is_dir():
                slides = sorted(image_path.glob("slide-*.png"))
                if 2 <= len(slides) <= 10:
                    bot.send_media_group(chat_id, slides, caption=f"🎠 Карусель {len(slides)} слайдов · {image_path.name}")
                    log(date, f"carousel sent: {len(slides)} slides from {image_path.relative_to(HERE)}")
                elif len(slides) == 1:
                    bot.send_photo(chat_id, slides[0], caption=f"🖼 Слайд · {slides[0].name}")
                    log(date, f"carousel had only 1 slide, sent as photo")
                else:
                    bot.send_message(chat_id, f"⚠️ <b>Карусель пуста или больше 10 слайдов:</b> {len(slides)} файлов в {image_rel}")
                    log(date, f"WARN carousel invalid slide count: {len(slides)}")
            else:
                bot.send_message(chat_id, f"⚠️ <b>Папка карусели не найдена:</b> <code>{bot.html_escape(image_rel)}</code>")
                log(date, f"WARN carousel folder missing: {image_rel}")
        else:
            # одна картинка
            if image_path.exists() and image_path.is_file():
                bot.send_photo(chat_id, image_path, caption=f"🖼 Картинка к посту · {image_path.name}")
                log(date, f"image sent: {image_path.relative_to(HERE)}")
            else:
                bot.send_message(
                    chat_id,
                    f"⚠️ <b>Картинка не найдена:</b> <code>{bot.html_escape(image_rel)}</code>\nПост уходит без визуала.",
                )
                log(date, f"WARN image missing: {image_rel}")

    # 3) текст поста — в <pre>-блоке для one-tap copy
    bot.send_message(
        chat_id,
        f"📝 <b>Текст поста</b> <i>(тапни — скопируется)</i>\n<pre>{bot.html_escape(body.strip())}</pre>",
        disable_preview=True,
    )

    # 4) голосовое — отдельной инструкцией
    if is_voice:
        duration = meta.get("voice_duration_sec", "60–90")
        hint = meta.get("voice_hint", "")
        msg = (
            f"🎤 <b>Голосовое</b>\n"
            f"Длина: {duration} секунд. Тон: разговорный.\n"
            f"{('Подсказка: ' + bot.html_escape(hint)) if hint else ''}\n\n"
            f"Прочитай вслух как написано (или своими словами по смыслу), запиши и отправь в канал."
        )
        bot.send_message(chat_id, msg)
        log(date, "voice instruction sent")

    # 5) опрос
    if poll and isinstance(poll, dict):
        question = poll.get("question", "")
        options = poll.get("options", [])
        msg_lines = [
            "🗳 <b>Создай опрос в канале</b>",
            f"<b>Вопрос:</b> {bot.html_escape(question)}",
            "<b>Варианты:</b>",
        ]
        for i, opt in enumerate(options, 1):
            msg_lines.append(f"{i}. {bot.html_escape(str(opt))}")
        msg_lines.append("\n<i>Голосование закрытое (анонимное).</i>")
        bot.send_message(chat_id, "\n".join(msg_lines))
        log(date, "poll instruction sent")

    # 6) CTA напоминание
    if is_cta:
        bot.send_message(
            chat_id,
            f"📣 <b>CTA в этом посте — уровень {cta_level}</b>\n"
            f"<i>Сегодняшний пост — единственный за неделю с прямым приглашением в личку.</i>\n"
            f"Проверь, что handle в посте корректный (@IVAN_SUNSIDE → твой реальный).",
        )

    # 7) финал
    bot.send_message(chat_id, "✅ <b>Пакет дня доставлен.</b>")
    log(date, f"delivery OK: {json.dumps(summary, ensure_ascii=False)}")

    return summary


# --- fallback при отсутствии файла ----------------------------------------

def notify_missing(date: dt.date) -> None:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
    weekday_ru = WEEKDAY_RU.get(WEEKDAY_CODES[date.weekday()], "")
    bot.send_message(
        chat_id,
        f"⚠️ <b>На {date.strftime('%d.%m.%Y')} ({weekday_ru}) нет подготовленного поста.</b>\n\n"
        f"Ожидаемый путь:\n"
        f"<code>.business/marketing/telegram-daily/drafts/{date.isocalendar().year}-W{date.isocalendar().week:02d}/{date.isoformat()}-*.md</code>\n\n"
        f"Возможные причины:\n"
        f"• Темник на эту неделю не заполнен (см. <code>weeks/</code>)\n"
        f"• V2-генератор ещё не запущен для этой даты\n"
        f"• Файл сломался / переименован\n\n"
        f"Что делать: запусти ручную публикацию или дозаполни темник на неделю.",
    )


# --- ошибки --------------------------------------------------------------

def notify_error(date: dt.date, err: Exception) -> None:
    try:
        chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))[-1500:]
        bot.send_message(
            chat_id,
            f"❌ <b>Ошибка ежедневной публикации {date.isoformat()}</b>\n\n"
            f"<code>{bot.html_escape(str(err))}</code>\n\n"
            f"Traceback (последние строки):\n"
            f"<pre>{bot.html_escape(tb)}</pre>\n\n"
            f"Лог: <code>.business/marketing/telegram-daily/logs/dispatch-{date.isoformat()}.log</code>",
        )
    except Exception as exc:
        # Бот не доступен — пишем только в лог
        log(date, f"notify_error FAILED: {exc}")


# --- main ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="Дата ISO YYYY-MM-DD (по умолчанию — сегодня)")
    parser.add_argument("--force", action="store_true", help="Игнорировать lock-файл")
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять в бот, только посчитать")
    args = parser.parse_args()

    if args.date:
        try:
            today = dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"✗ Невалидная дата: {args.date}", file=sys.stderr)
            return 1
    else:
        today = dt.date.today()

    log(today, f"START dispatcher · today={today.isoformat()} · force={args.force} · dry={args.dry_run}")

    # Старая защита: общий lock на день (обратная совместимость W22)
    if not args.force and not args.dry_run and already_sent(today):
        log(today, f"SKIP — общий lock на день уже стоит (W22-стиль)")
        return 0

    post_files = find_all_post_files(today)
    if not post_files:
        log(today, f"MISSING — нет файлов на {today.isoformat()}")
        if not args.dry_run:
            try:
                notify_missing(today)
            except Exception as exc:
                log(today, f"notify_missing FAILED: {exc}")
        return 2

    log(today, f"FOUND {len(post_files)} post(s): " + ", ".join(p.name for p in post_files))

    delivered = 0
    failed = 0

    for post_path in post_files:
        # Достаём rubric из имени файла YYYY-MM-DD-<weekday>-<rubric>.md
        stem_parts = post_path.stem.split("-")
        rubric = "-".join(stem_parts[4:]) if len(stem_parts) >= 5 else "unknown"

        if not args.force and not args.dry_run and already_sent(today, rubric):
            log(today, f"SKIP · {rubric} · уже отправлен (lock: sent-{today.isoformat()}-{rubric}.lock)")
            continue

        log(today, f"DELIVER · {rubric} · {post_path.name}")

        try:
            info = deliver(today, post_path, dry_run=args.dry_run)
        except Exception as exc:
            log(today, f"FATAL · {rubric}: {exc}\n{traceback.format_exc()}")
            notify_error(today, exc)
            failed += 1
            continue

        if not args.dry_run:
            mark_sent(today, rubric, info)
            log(today, f"DONE · {rubric} · lock created")
        delivered += 1

    log(today, f"FINISH · delivered={delivered} · failed={failed}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
