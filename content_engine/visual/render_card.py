"""Рендер HTML → PNG через Playwright Chromium.

Заменяет локальный render.ps1 (который использовал Edge на Windows).
Работает на сервере (Linux) и локально.

Использование как модуль:
    from render_card import render_html, render_dir
    render_html(Path("slide.html"), Path("slide.png"))
    render_dir(Path("html_dir"), Path("png_dir"))  # все slide-*.html → PNG

CLI:
    python render_card.py <input.html> <output.png>
    python render_card.py --dir <html_dir> <png_dir>

Оптимизировано под 2GB RAM:
  - single-process Chromium
  - закрываем браузер сразу после рендера
  - networkidle + пауза для загрузки шрифтов с Google Fonts CDN
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_W = 1080
DEFAULT_H = 1350

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",   # критично для контейнеров/малой RAM
    "--single-process",          # экономия памяти на 2GB сервере
    "--hide-scrollbars",
]


def render_html(html_path: Path, png_path: Path, width: int = DEFAULT_W, height: int = DEFAULT_H,
                wait_fonts_ms: int = 1800) -> Path:
    """Рендерит один HTML-файл в PNG. Возвращает путь к PNG."""
    from playwright.sync_api import sync_playwright

    html_path = Path(html_path).resolve()
    png_path = Path(png_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.goto(f"file://{html_path}", wait_until="load", timeout=30000)
            # ждём подгрузку шрифтов с Google Fonts CDN
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # доп. ожидание + явная проверка готовности шрифтов
            try:
                page.evaluate("document.fonts.ready")
            except Exception:
                pass
            page.wait_for_timeout(wait_fonts_ms)
            page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": width, "height": height})
        finally:
            browser.close()

    return png_path


def render_dir(html_dir: Path, png_dir: Path, pattern: str = "slide-*.html") -> list[Path]:
    """Рендерит все HTML по паттерну из html_dir в png_dir. Возвращает список PNG."""
    html_dir = Path(html_dir)
    png_dir = Path(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for html_file in sorted(html_dir.glob(pattern)):
        png_file = png_dir / (html_file.stem + ".png")
        render_html(html_file, png_file)
        results.append(png_file)
        print(f"  ✓ {html_file.name} → {png_file.name}")
    return results


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("Usage:\n  render_card.py <input.html> <output.png>\n  render_card.py --dir <html_dir> <png_dir>")
        return 1

    if args[0] == "--dir":
        html_dir, png_dir = Path(args[1]), Path(args[2])
        pngs = render_dir(html_dir, png_dir)
        print(f"[render] ✓ {len(pngs)} PNG в {png_dir}")
    else:
        inp, outp = Path(args[0]), Path(args[1])
        render_html(inp, outp)
        print(f"[render] ✓ {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
