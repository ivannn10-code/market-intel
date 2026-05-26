"""Отправка готовой карусели в Telegram-бот для Ивана.

Использование:
    python send_carousel.py <путь_к_папке_карусели>

Папка должна содержать:
    - png/slide-01.png ... slide-NN.png  (готовые слайды)
    - <slug>.md (рядом с папкой или внутри) с секциями:
        ## Подпись под публикацией
        ## Хэштеги
        ## Первый комментарий

Бот шлёт 4 сообщения в чат TELEGRAM_BOT_CHAT_ID:
    1. Альбом из 2-10 PNG (sendMediaGroup) — сама карусель
    2. Подпись под публикацией в <pre>-блоке (one-tap copy)
    3. Хэштеги в <pre>-блоке
    4. Первый комментарий в <pre>-блоке

Все текстовые блоки оборачиваются в <pre>, чтобы Telegram показал кнопку
«Copy» при тапе — Иван копирует одним нажатием и вставляет в Instagram.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot
import config


def find_md_file(carousel_dir: Path) -> Path:
    """Найти MD-файл карусели. Сначала ищем внутри папки, потом рядом."""
    inside = list(carousel_dir.glob("*.md"))
    if inside:
        for p in inside:
            if p.name.lower() not in {"readme.md", "index.md"}:
                return p
        return inside[0]

    parent = carousel_dir.parent
    sibling = parent / f"{carousel_dir.name}.md"
    if sibling.exists():
        return sibling

    candidates = list(parent.glob(f"{carousel_dir.name}*.md"))
    if candidates:
        return candidates[0]

    raise FileNotFoundError(
        f"Не нашёл MD-файл карусели ни внутри {carousel_dir}, ни рядом с ней"
    )


def parse_md_sections(md_path: Path) -> dict[str, str]:
    """Достать секции из MD по заголовкам H2.

    Возвращает dict: ключ — заголовок (lowercased, без ##), значение — текст секции.
    Внутри секций вырезаем blockquote-маркеры (>), markdown-обёртки.
    """
    raw = md_path.read_text(encoding="utf-8")

    sections: dict[str, str] = {}
    current_title: str | None = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        h2_match = re.match(r"^##\s+(.+?)\s*$", line)
        if h2_match:
            if current_title is not None:
                sections[current_title.lower()] = "\n".join(current_lines).strip()
            current_title = h2_match.group(1).strip()
            current_lines = []
            continue

        if line.startswith("# "):
            if current_title is not None:
                sections[current_title.lower()] = "\n".join(current_lines).strip()
                current_title = None
                current_lines = []
            continue

        if line.startswith("### ") or line.startswith("---"):
            if current_title is not None:
                sections[current_title.lower()] = "\n".join(current_lines).strip()
                current_title = None
                current_lines = []
            continue

        if current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections[current_title.lower()] = "\n".join(current_lines).strip()

    return sections


def clean_section(text: str) -> str:
    """Убрать blockquote-маркеры (>) и лишние пустые строки, оставить только то,
    что Иван реально скопирует в Instagram."""
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        cleaned_lines.append(stripped)

    out = "\n".join(cleaned_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def collect_slides(carousel_dir: Path) -> list[Path]:
    png_dir = carousel_dir / "png"
    if not png_dir.exists():
        raise FileNotFoundError(f"Нет папки png/ в {carousel_dir}")

    slides = sorted(png_dir.glob("slide-*.png"))
    if not slides:
        raise FileNotFoundError(f"В {png_dir} нет файлов slide-*.png")

    if len(slides) > 10:
        print(f"[warn] Найдено {len(slides)} слайдов, отправлю первые 10 (лимит Telegram)")
        slides = slides[:10]

    return slides


def send_carousel(carousel_dir: Path, force: bool = False) -> None:
    chat_id = config.env("TELEGRAM_BOT_CHAT_ID", required=True)

    # Idempotency-маркер. Защита от двойной отправки (например, из-за гонки
    # с фоновой сессией resume-протокола). Маркер кладётся рядом с PNG-папкой.
    delivered_marker = carousel_dir / ".delivered"
    if delivered_marker.exists() and not force:
        ts = delivered_marker.read_text(encoding="utf-8").strip()
        raise RuntimeError(
            f"Карусель уже была отправлена ({ts}). "
            f"Если действительно нужно отправить ещё раз — запусти с флагом --force "
            f"или удали файл {delivered_marker}"
        )

    md_path = find_md_file(carousel_dir)
    sections = parse_md_sections(md_path)
    slides = collect_slides(carousel_dir)

    caption = clean_section(sections.get("подпись под публикацией", ""))
    hashtags = clean_section(sections.get("хэштеги", ""))
    first_comment = clean_section(sections.get("первый комментарий", ""))

    title = carousel_dir.name

    print(f"[publisher] Карусель: {title}")
    print(f"[publisher] Слайдов: {len(slides)}")
    print(f"[publisher] Подпись: {len(caption)} знаков")
    print(f"[publisher] Хэштеги: {bool(hashtags)}")
    print(f"[publisher] Первый коммент: {bool(first_comment)}")
    print(f"[publisher] Чат: {chat_id}")

    header = (
        f"📤 <b>Карусель готова к публикации</b>\n"
        f"<i>{bot.html_escape(title)}</i>\n\n"
        f"Ниже: 1) альбом слайдов, 2) подпись, 3) хэштеги, 4) первый комментарий.\n"
        f"Тапни на блок текста — скопируется одним нажатием."
    )
    bot.send_message(chat_id, header)
    time.sleep(0.6)

    print(f"[publisher] → media group ({len(slides)} слайдов)")
    bot.send_media_group(chat_id, slides, caption="")
    time.sleep(1.2)

    if caption:
        print("[publisher] → caption block")
        msg = (
            "📝 <b>Подпись под публикацией</b>\n"
            f"<pre>{bot.html_escape(caption)}</pre>"
        )
        bot.send_message(chat_id, msg, disable_preview=True)
        time.sleep(0.6)

    if hashtags:
        print("[publisher] → hashtags block")
        msg = (
            "🏷 <b>Хэштеги</b>\n"
            f"<pre>{bot.html_escape(hashtags)}</pre>"
        )
        bot.send_message(chat_id, msg, disable_preview=True)
        time.sleep(0.6)

    if first_comment:
        print("[publisher] → first comment block")
        msg = (
            "💬 <b>Первый комментарий</b> <i>(публикуй сразу после поста под ним же)</i>\n"
            f"<pre>{bot.html_escape(first_comment)}</pre>"
        )
        bot.send_message(chat_id, msg, disable_preview=True)
        time.sleep(0.6)

    bot.send_message(chat_id, "✅ Готово. Карусель и тексты доставлены.")
    print("[publisher] ✓ Done.")

    # Запоминаем факт успешной доставки — защита от повторной отправки
    delivered_marker.write_text(
        f"delivered {time.strftime('%Y-%m-%d %H:%M:%S')} chat={chat_id} slides={len(slides)}",
        encoding="utf-8",
    )


def main() -> int:
    args = sys.argv[1:]
    force = False
    positional = []
    for a in args:
        if a in ("--force", "-f"):
            force = True
        else:
            positional.append(a)

    if not positional:
        print("usage: python send_carousel.py <путь_к_папке_карусели> [--force]")
        return 1

    carousel_dir = Path(positional[0]).resolve()
    if not carousel_dir.exists():
        print(f"Папка не найдена: {carousel_dir}")
        return 1
    if not carousel_dir.is_dir():
        print(f"Это не папка: {carousel_dir}")
        return 1

    try:
        send_carousel(carousel_dir, force=force)
        return 0
    except Exception as exc:
        print(f"[publisher] ✗ Ошибка: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
