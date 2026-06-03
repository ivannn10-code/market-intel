"""Лид-магнит B · «7 параметров сравнения офисов класса А» (5 страниц с AI-фонами).

5 страниц A4 портрет, тёмная палитра v4.0, для сегментов:
  — Бизнесы под собственный офис
  — Инвесторы в коммерческую недвижимость (yield + ликвидность)

Структура:
  1. Обложка
  2. Параметры 1-2 · «Локация и финансовая модель»
  3. Параметры 3-5 · «Здание и собственник»
  4. Параметры 6-7 · «Инженерия и арендаторы»
  5. CTA (код ОФИС)

Цифры опираются на публичные ежегодные обзоры Cushman & Wakefield, JLL, Knight Frank,
Colliers + 214/41/ФЗ + Росреестр. Без названий конкретных БЦ.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "visual"))  # ai_bg

from build import render_html_to_pdf


# ── Контент 7 параметров (по группам) ───────────────────────────────────────

PARAMS = [
    # Группа 1: Локация и финансовая модель (page 2)
    {"q": "Локация и доступность — ≤7 минут пешком до метро, парковочный коэффициент.",
     "e": "Класс А — ≤7 мин пешком до станции, ≤500-700 м. Парковка: 1 машино-место на 60-80 м² арендуемой (в Сити часто 1:200, что считается дефицитом).",
     "f": "Метро «в шаговой» 15+ минут или «достроят к 2030» — закладывайте дисконт в IRR."},
    {"q": "Цена входа vs аренда — IRR, cap rate, срок окупаемости?",
     "e": "Текущая ставка аренды в Москве, класс А (центр): 30-60 тыс ₽/м²/год без НДС (2026). Cap rate класса А: 8-11%. Срок окупаемости при покупке — 10-13 лет без индексации, 8-11 с ней.",
     "f": "«Аренда по запросу» — не сравнить с рынком. Требуйте цифры по соседним объектам в кластере."},
    # Группа 2: Здание и собственник (page 3)
    {"q": "Технические параметры здания — Grade A признаки по факту?",
     "e": "Высота потолков 3+ м от плиты до плиты, шаг колонн 6-9 м, открывающиеся окна или фрамуги, BMS (Building Management System), серверная 1 на 5000 м².",
     "f": "«Класс А» в рекламе ≠ класс А по факту. Проверяйте чек-листом Cushman/JLL/Knight Frank."},
    {"q": "Юридическая чистота: собственник, история объекта, обременения?",
     "e": "Собственник публичный или закрытый? История смены собственников за 10 лет, залоги, обременения, аресты, банкротства — проверяется в Росреестре и kad.arbitr.ru по ИНН.",
     "f": "Объект в залоге у банка с проблемами или собственник банкротится — ваш выход зависит от удачи."},
    {"q": "ВРИ участка — «деловое управление» или «коммерческое»? Не «производственное / складское»?",
     "e": "Вид разрешённого использования публичен в Росреестре. Только «деловое управление» / «общественно-деловое» позволяет полноценный офис класса А.",
     "f": "ВРИ «производство» с переоформлением «по ходу» — риск приостановки или невозможности расширения."},
    # Группа 3: Инженерия и арендаторы (page 4)
    {"q": "Управляющая компания и OPEX — тариф, опыт работы с классом А, рейтинг?",
     "e": "OPEX класса А в Москве 2026: 6-12 тыс ₽/м²/год без НДС. Часы работы security и инженерного обслуживания 24/7 — норма. Опыт УК с классом А — критично.",
     "f": "OPEX «уточним позже» = +20-50% к расчётной экономике объекта. Цифру требуйте на встрече."},
    {"q": "Арендаторы и репутация БЦ — структура tenants и ликвидность при выходе?",
     "e": "Mix крупных арендаторов (Big4, банки, IT, fintech) > 50% = устойчивость. Сменяемость <20% в год — здоровая динамика. Репутация в индустрии проверяется у брокеров (Cushman, JLL, Knight Frank).",
     "f": "Объект «никто не знает» в индустрии = низкая ликвидность при перепродаже и сложный найм арендаторов."},
]

PAGE_TAGS = [
    "Локация и финансовая модель",    # стр. 2 (Q1-Q2)
    "Здание и собственник",           # стр. 3 (Q3-Q5)
    "Инженерия и арендаторы",         # стр. 4 (Q6-Q7)
]

# Сколько параметров на каждой content-странице (3 страницы)
ITEMS_PER_PAGE = [2, 3, 2]

# AI-фоны: коммерческая премиум-эстетика, единый стиль
BG_HINTS = {
    1: "panoramic floor-to-ceiling glass facade of a modern class A office building at dawn, blurred business district skyline visible through reflective glass, deep teal-navy tones, premium editorial photography, no people, no specific recognizable building",
    2: "modern empty conference room with floor-to-ceiling windows overlooking a city, polished concrete floor, minimalist long wooden table, leather chairs, warm directional light from one side, premium aesthetic, no people",
    3: "architectural floor plan of a modern office layout on a dark wooden surface, scale ruler, technical pen, top-down editorial view, premium documentation aesthetic, soft side light",
    4: "premium office reception lobby with polished marble counter, brass details, modern lighting, leather seating, no people, evening warm light, contemplative atmosphere",
    5: "premium executive office at dusk with city lights visible through floor-to-ceiling glass window, a single large leather chair facing the window, polished wood desk with closed laptop, brass desk lamp casting warm light, contemplative mood",
}

META = {
    "tag": "Чек-лист · бесплатно",
    "title": "7 параметров\nоценки офиса<br>класса А",
    "subtitle": "Чек-лист, по которому я сравниваю объекты перед сделкой — для собственника или инвестора. То, на что смотрят брокеры Cushman, JLL, Knight Frank до отправки клиента в шорт-лист.",
    "title_anchor_label": "параметров до подписания договора",
    "title_anchor_num": "7",
    "epigraph": "Хороший офис класса А виден за 15 минут.<br>Плохой — раскрывается через 5 лет аренды.<br>Эти 7 параметров отделяют одно от другого.",
}

CTA = {
    "tag": "Решаю задачу клиента — лично",
    "headline": "Хотите подобрать офис<br>под вашу задачу — лично со мной?",
    "lead": "Пришлите кодовое слово в Telegram, SMS или звонком",
    "code": "ОФИС",
    "tg": "@IVAN_SUNSIDE",
    "tg_url": "https://t.me/IVAN_SUNSIDE",
    "phone_display": "+7 (925) 078-80-90",
    "phone_tel": "+79250788090",
    "author_name": "Иван Гладышев",
    "author_meta": "Недвижимость Москвы · 12 лет на рынке",
}

CODE = "ОФИС"


# ── CSS: тёмная палитра v4.0 (повторяет a_spisok для единства фирстиля) ────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&display=swap');
@page { size: A4 portrait; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
:root {
  --bg: #0F3D4A;
  --text: #E7E2D8;
  --accent: #FF5A2A;
  --steel: #4A6A7B;
  --muted: rgba(231,226,216,0.62);
  --line: rgba(231,226,216,0.18);
}
html, body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; -webkit-font-smoothing: antialiased; }

.page {
  width: 210mm; min-height: 297mm; padding: 14mm 18mm 12mm 18mm;
  position: relative; color: var(--text);
  background-color: var(--bg); background-size: cover; background-position: center; background-repeat: no-repeat;
  display: flex; flex-direction: column;
  page-break-after: always;
}
.page:last-child { page-break-after: auto; }
.page::before {
  content: ""; position: absolute; inset: 0; z-index: 1;
  background: linear-gradient(180deg,
    rgba(11,46,56,0.92) 0%, rgba(11,46,56,0.78) 32%,
    rgba(11,46,56,0.66) 56%, rgba(11,46,56,0.86) 100%);
}
.page > * { position: relative; z-index: 2; }
.page > .foot { margin-top: auto; }

.brand-strip {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 8.5pt; letter-spacing: 1.8pt; text-transform: uppercase;
  color: var(--muted); font-weight: 600;
  padding-bottom: 4mm; border-bottom: 1px solid var(--line);
}
.brand-strip .mark { color: var(--accent); margin-right: 7px; font-size: 11pt; line-height: 0; }

.foot {
  display: flex; justify-content: space-between; align-items: center;
  padding-top: 4mm; border-top: 1px solid var(--line);
  font-size: 8pt; letter-spacing: 0.9pt; text-transform: uppercase;
  color: var(--muted); font-weight: 600;
}

/* === COVER === */
.cover-epigraph {
  margin-top: 16mm; max-width: 120mm; margin-left: auto;
  text-align: right; padding: 6mm 8mm;
  background: rgba(11,46,56,0.62); border-radius: 4mm;
  border-right: 3px solid var(--accent);
  box-shadow: 0 4mm 14mm rgba(0,0,0,0.22);
  font-family: 'PT Serif', serif; font-style: italic; font-weight: 400;
  font-size: 14pt; line-height: 1.35; color: var(--accent);
}
.cover-body { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; padding-bottom: 6mm; }
.cover-tag {
  display: inline-flex; align-self: flex-start;
  font-size: 9.5pt; letter-spacing: 2.4pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600;
  border-left: 3px solid var(--accent); padding: 3px 0 3px 12px;
  margin-bottom: 8mm;
}
.cover-title {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 46pt; line-height: 1.02; letter-spacing: -1pt;
  color: var(--text); white-space: pre-line;
  text-shadow: 0 2px 24px rgba(0,0,0,0.45);
}
.cover-subtitle {
  font-size: 12pt; line-height: 1.55; color: rgba(231,226,216,0.82);
  margin-top: 7mm; max-width: 150mm;
}
.cover-stat { margin-top: 10mm; display: inline-flex; align-items: baseline; gap: 5mm; }
.cover-stat .v {
  font-family: 'PT Serif', serif; font-weight: 700; font-style: italic;
  font-size: 56pt; line-height: 1; color: var(--accent); letter-spacing: -2pt;
}
.cover-stat .l {
  font-size: 9pt; letter-spacing: 2pt; text-transform: uppercase;
  color: rgba(231,226,216,0.7); max-width: 50mm; line-height: 1.4;
}

/* === CONTENT === */
.content-body { flex: 1; display: flex; flex-direction: column; padding-top: 6mm; }
.content-tag {
  display: inline-flex; align-self: flex-start;
  font-size: 9pt; letter-spacing: 2.4pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600;
  border-left: 3px solid var(--accent); padding: 3px 0 3px 11px;
  margin-bottom: 7mm;
}
.q {
  display: grid; grid-template-columns: 14mm 1fr; gap: 4mm;
  padding: 3.5mm 0;
}
.q + .q { border-top: 1px solid var(--line); }
.q .num {
  font-family: 'PT Serif', serif; font-weight: 700; font-style: italic;
  font-size: 26pt; line-height: 1; color: var(--accent);
  letter-spacing: -1pt;
}
.q .body { display: flex; flex-direction: column; gap: 1.5mm; }
.q .question {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 11.5pt; line-height: 1.25; color: var(--text);
  text-shadow: 0 1px 14px rgba(0,0,0,0.4);
}
.q .explain {
  font-size: 9.5pt; line-height: 1.45; color: rgba(231,226,216,0.86);
}
.q .flag {
  font-size: 9pt; line-height: 1.4; color: #FFD0BF; font-weight: 500;
  background: rgba(255,90,42,0.13); padding: 1.8mm 2.5mm;
  border-radius: 1.5mm; border-left: 2px solid var(--accent);
  margin-top: 0.5mm;
}

/* === CTA === */
.cta-body { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 6mm 0; }
.cta-card {
  background: rgba(11,46,56,0.88); border-radius: 6mm;
  padding: 14mm 12mm 11mm 12mm; position: relative; overflow: hidden;
  border: 1px solid rgba(231,226,216,0.12);
  box-shadow: 0 10mm 30mm rgba(0,0,0,0.35);
}
.cta-card::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: 5mm; background: var(--accent);
}
.cta-card::after {
  content: ""; position: absolute; top: -20mm; right: -20mm;
  width: 70mm; height: 70mm; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,90,42,0.32) 0%, rgba(255,90,42,0) 65%);
}
.cta-tag {
  font-size: 9pt; letter-spacing: 2.4pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600; padding-left: 2mm;
}
.cta-headline {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 22pt; line-height: 1.18; margin-top: 4mm; padding-left: 2mm;
  color: var(--text);
}
.cta-lead {
  font-size: 11pt; line-height: 1.5; margin-top: 6mm; padding-left: 2mm;
  color: rgba(231,226,216,0.85);
}
.cta-code {
  display: inline-block; margin-top: 5mm; margin-left: 2mm;
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 28pt; letter-spacing: 2.5pt; color: var(--accent);
  padding: 3mm 9mm; border: 1.8px solid var(--accent); border-radius: 2.5mm;
  background: rgba(255,90,42,0.08);
}
.cta-contacts { margin-top: 8mm; padding-left: 2mm; font-size: 11pt; line-height: 1.7; }
.cta-contacts a { color: var(--accent); text-decoration: none; font-weight: 600; }
.cta-contacts .label {
  display: inline-block; min-width: 28mm;
  color: rgba(231,226,216,0.55);
  text-transform: uppercase; letter-spacing: 1.2pt; font-size: 8.5pt; font-weight: 600;
}
.cta-author {
  margin-top: 9mm; padding-left: 2mm; padding-top: 4mm;
  border-top: 1px solid rgba(231,226,216,0.18);
}
.cta-author-name { font-family: 'PT Serif', serif; font-weight: 700; font-size: 13pt; color: var(--text); }
.cta-author-meta {
  font-size: 9pt; letter-spacing: 0.6pt; color: rgba(231,226,216,0.7);
  margin-top: 1.5mm; text-transform: uppercase; font-weight: 500;
}
"""


# ── AI-фоны ─────────────────────────────────────────────────────────────────

def _generate_backgrounds(out_dir: Path) -> dict[int, str]:
    try:
        from ai_bg import generate_bg, build_bg_prompt, is_available
    except Exception as exc:
        print(f"[B] ai_bg недоступен: {exc}"); return {}
    if not is_available():
        print("[B] GEMINI_API_KEY нет — без AI-фонов"); return {}

    out_dir.mkdir(parents=True, exist_ok=True)

    def gen_one(num: int, hint: str):
        existing = out_dir / f"bg-{num}.png"
        if existing.exists() and existing.stat().st_size > 50_000:
            print(f"[B] = bg-{num}.png exists, reuse ({existing.stat().st_size // 1024} KB)")
            return num, existing.name
        try:
            path = out_dir / f"bg-{num}.png"
            generate_bg(build_bg_prompt(hint), path)
            print(f"[B] ✓ bg-{num}.png ({path.stat().st_size // 1024} KB)")
            return num, path.name
        except Exception as exc:
            print(f"[B] ✗ bg-{num} failed: {exc}"); return num, None

    result: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(gen_one, n, h) for n, h in BG_HINTS.items()]
        for f in futs:
            n, name = f.result()
            if name:
                result[n] = name
    print(f"[B] AI-фоны: {len(result)}/{len(BG_HINTS)} успешно")
    return result


# ── Сборка HTML ─────────────────────────────────────────────────────────────

def _brand_strip(page_label: str) -> str:
    return (
        '<div class="brand-strip">'
        '<div><span class="mark">✱</span>ИГ · НЕДВИЖИМОСТЬ МОСКВЫ</div>'
        f'<div>{page_label}</div></div>'
    )


def _foot(page_num: int, total: int) -> str:
    return (
        '<div class="foot">'
        '<div>Иван Гладышев · Недвижимость Москвы</div>'
        f'<div>Код выдачи · {CODE} · {page_num:02d} / {total:02d}</div>'
        '</div>'
    )


def _page_open(idx: int, bgs: dict[int, str]) -> str:
    bg = bgs.get(idx)
    style = f' style="background-image:url(\'{bg}\');"' if bg else ""
    return f'<div class="page"{style}>'


def _render_params(items: list[dict], start: int) -> str:
    out = []
    for i, q in enumerate(items, start=start):
        out.append(
            f'<div class="q"><div class="num">{i:02d}</div>'
            f'<div class="body">'
            f'<div class="question">{q["q"]}</div>'
            f'<div class="explain">{q["e"]}</div>'
            f'<div class="flag">🚩 {q["f"]}</div>'
            f'</div></div>'
        )
    return "".join(out)


def build_html(bgs: dict[int, str]) -> str:
    total = 5

    page1 = (
        _page_open(1, bgs)
        + _brand_strip(f"Чек-лист · 01 / {total:02d}")
        + f'<div class="cover-epigraph">{META["epigraph"]}</div>'
        + '<div class="cover-body">'
        + f'<div class="cover-tag">{META["tag"]}</div>'
        + f'<div class="cover-title">{META["title"]}</div>'
        + f'<div class="cover-subtitle">{META["subtitle"]}</div>'
        + '<div class="cover-stat">'
        + f'<span class="v">{META["title_anchor_num"]}</span>'
        + f'<span class="l">{META["title_anchor_label"]}</span>'
        + '</div></div>'
        + _foot(1, total)
        + '</div>'
    )

    content_pages = []
    cursor = 0
    for i, tag in enumerate(PAGE_TAGS):
        page_idx = 2 + i
        n_items = ITEMS_PER_PAGE[i]
        items = PARAMS[cursor:cursor + n_items]
        start = cursor + 1
        cursor += n_items
        page = (
            _page_open(page_idx, bgs)
            + _brand_strip(f"Чек-лист · {page_idx:02d} / {total:02d}")
            + '<div class="content-body">'
            + f'<div class="content-tag">{tag}</div>'
            + _render_params(items, start=start)
            + '</div>'
            + _foot(page_idx, total)
            + '</div>'
        )
        content_pages.append(page)

    cta_card = (
        '<div class="cta-card">'
        f'<div class="cta-tag">{CTA["tag"]}</div>'
        f'<div class="cta-headline">{CTA["headline"]}</div>'
        f'<div class="cta-lead">{CTA["lead"]}</div>'
        f'<div class="cta-code">{CTA["code"]}</div>'
        '<div class="cta-contacts">'
        f'<div><span class="label">Telegram</span><a href="{CTA["tg_url"]}">{CTA["tg"]}</a></div>'
        f'<div><span class="label">Звонок / SMS</span><a href="tel:{CTA["phone_tel"]}">{CTA["phone_display"]}</a></div>'
        '</div>'
        '<div class="cta-author">'
        f'<div class="cta-author-name">{CTA["author_name"]}</div>'
        f'<div class="cta-author-meta">{CTA["author_meta"]}</div>'
        '</div>'
        '</div>'
    )
    page5 = (
        _page_open(5, bgs)
        + _brand_strip(f"Чек-лист · 05 / {total:02d}")
        + '<div class="cta-body">' + cta_card + '</div>'
        + _foot(5, total)
        + '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        '<title>7 параметров оценки офиса класса А</title>'
        f'<style>{CSS}</style></head>'
        f'<body>{page1}{"".join(content_pages)}{page5}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "b_office"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[B] → генерю 5 AI-фонов (Gemini, параллельно, с reuse)...")
    bgs = _generate_backgrounds(out_dir)
    html_path = out_dir / "b_office.html"
    pdf_path = out_dir / "b_office.pdf"
    html_path.write_text(build_html(bgs), encoding="utf-8")
    print(f"[B] HTML записан: {html_path}")
    render_html_to_pdf(html_path, pdf_path)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"[B] ✓ PDF готов: {pdf_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
