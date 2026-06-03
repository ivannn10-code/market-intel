"""HTML → A4 PDF через Playwright Chromium. Под лид-магниты в фирстиле Ивана.

Использование:
    from build import render_html_to_pdf
    render_html_to_pdf(Path("magnet.html"), Path("magnet.pdf"))

Те же Chromium-аргументы что в render_card.py (под 2GB RAM сервер).
"""

from __future__ import annotations

from pathlib import Path

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--single-process",
    "--hide-scrollbars",
]


def render_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    fmt: str = "A4",
    margin_mm: tuple = (0, 0, 0, 0),
    wait_fonts_ms: int = 1800,
) -> Path:
    """Рендерит HTML в PDF. margin_mm = (top, right, bottom, left) в мм.
    По умолчанию margin=0 — пусть HTML сам управляет полями через .page padding."""
    from playwright.sync_api import sync_playwright

    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    mt, mr, mb, ml = margin_mm

    with sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        try:
            page = browser.new_page()
            page.goto(f"file://{html_path}", wait_until="load", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            try:
                page.evaluate("document.fonts.ready")
            except Exception:
                pass
            page.wait_for_timeout(wait_fonts_ms)
            page.pdf(
                path=str(pdf_path),
                format=fmt,
                print_background=True,
                margin={
                    "top": f"{mt}mm",
                    "right": f"{mr}mm",
                    "bottom": f"{mb}mm",
                    "left": f"{ml}mm",
                },
                prefer_css_page_size=True,
            )
        finally:
            browser.close()

    return pdf_path
