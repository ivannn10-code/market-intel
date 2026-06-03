"""Лид-магнит B v2 · «8 параметров оценки офиса класса А» (4 страницы, простой язык).

4 страницы A4 портрет, тёмная палитра v4.0, без виньеток (ровный лёгкий оверлей).
Язык — человеческий, для собственника или инвестора, без англицизмов и брокерского
жаргона. Каждый параметр объясняет ЗАЧЕМ важно, не просто что должно быть.

Структура:
  1. Обложка
  2. Параметры 1-4 · «Где, почём, как устроено»
  3. Параметры 5-8 · «Что вокруг и кто за этим стоит»
  4. CTA (код ОФИС)
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "visual"))

from build import render_html_to_pdf


# ── Контент 8 параметров (по 4 в группу) — простой язык ─────────────────────

PARAMS = [
    # Группа 1: Где, почём, как устроено
    {"q": "Можно ли дойти до метро пешком за 7-10 минут?",
     "e": "Это норма для класса А. Если дольше — команда теряет час в день, опаздывает, устаёт. Близость к ТТК или МКАД — для встреч с клиентами и поездок.",
     "f": "Метро в 15+ минутах или «обещают построить» — это уже не класс А, и цена должна быть с дисконтом."},
    {"q": "Что входит в цену аренды — узнайте полную ставку, не «голую».",
     "e": "Полная цена = аренда + эксплуатация + электричество + НДС. «Голая» ставка плюс эксплуатация — реальная цена вырастает на 30-50%. Индексация: 5-10% в год, в Москве сейчас до 15%.",
     "f": "«Цена по запросу» — обходите. Хороший арендодатель цены не прячет."},
    {"q": "Какие потолки, открываются ли окна, как с вентиляцией?",
     "e": "Для класса А — потолки от 3 метров. Низкие давят. Окна должны открываться или иметь фрамуги — без свежего воздуха люди устают за 4 часа. Большие панорамы — это не красота, это уровень освещения и впечатление клиентов.",
     "f": "Потолки 2,7 м и кондиционеры в окнах — это уровень класса B, не A. Не переплачивайте за слово в рекламе."},
    {"q": "Хватит ли парковки сотрудникам, гостям, грузовому транспорту?",
     "e": "Норма: 1 машино-место на 60-80 м² арендуемой площади. Команда 30 человек = минимум 15-20 мест + отдельные гостевые. Грузовая зона и грузовой лифт — обязательно для приёмки мебели/техники.",
     "f": "Гостевой парковки нет, грузовой лифт через парадный вход — комфорт сильно проседает с первого месяца."},
    # Группа 2: Что вокруг и кто за этим стоит
    {"q": "Есть ли резерв интернета и электричества?",
     "e": "Для серьёзного бизнеса в офисе должно быть два независимых провайдера интернета и генератор на случай отключения света. Час простоя для банка, IT-команды или юристов — это деньги и репутация.",
     "f": "Один провайдер и нет генератора — для серьёзного бизнеса риск. Простой = реальные потери, считайте."},
    {"q": "Кто арендует соседние офисы в этом БЦ?",
     "e": "Крупные банки, известные IT-компании, международные консалтинговые и юридические фирмы — знак качества. Спросите у соседей мнение об управляющей компании — самые честные отзывы получите там, не у арендодателя.",
     "f": "Соседи — мелкие неизвестные компании, кафе, нотариусы — это не уровень класса А. Ликвидность объекта при перепродаже ниже."},
    {"q": "Кто управляет зданием и сколько вы за это платите?",
     "e": "Хорошие управляющие компании Москвы все на слуху — спросите у брокера или соседей. Охрана и сервис в классе А работают 24/7, не «по будням до 18:00». Стоимость эксплуатации — обычно 6-12 тыс ₽ за квадрат в год.",
     "f": "УК «своя» от собственника без опыта класса А, тариф эксплуатации «уточним позже» — будут скрытые расходы и халтура в сервисе."},
    {"q": "Кто собственник здания, нет ли проблем с документами?",
     "e": "Узнайте, кто собственник — компания (предпочтительно публичная) или частное лицо. Здание в залоге или нет — это бесплатно проверяется в Росреестре за 5 минут. Назначение участка должно быть «деловое управление», не «склад» или «промышленность».",
     "f": "Здание в залоге, собственник в банкротстве или назначение участка «не то» — любая проблема может сорвать договор."},
]

PAGE_TAGS = [
    "Где, почём, как устроено",        # стр. 2 (Q1-Q4)
    "Что вокруг и кто за этим стоит",  # стр. 3 (Q5-Q8)
]

ITEMS_PER_PAGE = [4, 4]
TOTAL_PAGES = 4

# AI-фоны: коммерческая премиум-эстетика (4 страницы)
BG_HINTS = {
    1: "panoramic floor-to-ceiling glass facade of a modern class A office building at dawn, blurred business district skyline visible through reflective glass, deep teal-navy tones, premium editorial photography, no people, no specific recognizable building",
    2: "modern empty conference room with floor-to-ceiling windows overlooking a city, polished concrete floor, minimalist long wooden table, leather chairs, warm directional light from one side, premium aesthetic, no people",
    3: "architectural floor plan of a modern office layout on a dark wooden surface, scale ruler, technical pen, top-down editorial view, premium documentation aesthetic, soft side light",
    4: "premium executive office at dusk with city lights visible through floor-to-ceiling glass window, a single large leather chair facing the window, polished wood desk with closed laptop, brass desk lamp casting warm light, contemplative mood",
}

META = {
    "tag": "Чек-лист · бесплатно",
    "title": "8 параметров\nоценки офиса<br>класса А",
    "subtitle": "Простой чек-лист на одну встречу с арендодателем — для собственника или инвестора. Без брокерского жаргона. Только то, что вы можете увидеть и проверить сами.",
    "title_anchor_label": "параметров до подписания",
    "title_anchor_num": "8",
    "epigraph": "Хороший офис класса А виден за 15 минут.<br>Плохой — раскрывается через 5 лет аренды.<br>Эти 8 параметров отделяют одно от другого.",
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


# ── CSS: тёмная палитра v4.0, БЕЗ виньетки (ровный лёгкий оверлей) ──────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&display=swap');
@page { size: A4 portrait; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
:root {
  --bg: #0F3D4A;
  --text: #E7E2D8;
  --accent: #FF5A2A;
  --steel: #4A6A7B;
  --muted: rgba(231,226,216,0.68);
  --line: rgba(231,226,216,0.20);
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

/* РОВНЫЙ оверлей без виньетки — фон фото видно равномерно */
.page::before {
  content: ""; position: absolute; inset: 0; z-index: 1;
  background: rgba(11,46,56,0.55);
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
  text-shadow: 0 2px 24px rgba(0,0,0,0.55);
}
.cover-subtitle {
  font-size: 12pt; line-height: 1.55; color: rgba(231,226,216,0.88);
  margin-top: 7mm; max-width: 150mm;
  text-shadow: 0 1px 10px rgba(0,0,0,0.4);
}
.cover-stat { margin-top: 10mm; display: inline-flex; align-items: baseline; gap: 5mm; }
.cover-stat .v {
  font-family: 'PT Serif', serif; font-weight: 700; font-style: italic;
  font-size: 56pt; line-height: 1; color: var(--accent); letter-spacing: -2pt;
  text-shadow: 0 2px 16px rgba(0,0,0,0.5);
}
.cover-stat .l {
  font-size: 9pt; letter-spacing: 2pt; text-transform: uppercase;
  color: rgba(231,226,216,0.78); max-width: 50mm; line-height: 1.4;
}

/* === CONTENT === */
.content-body { flex: 1; display: flex; flex-direction: column; justify-content: space-between; padding-top: 6mm; }
.content-tag {
  display: inline-flex; align-self: flex-start;
  font-size: 9pt; letter-spacing: 2.4pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600;
  border-left: 3px solid var(--accent); padding: 3px 0 3px 11px;
  margin-bottom: 7mm;
}
.questions { flex: 1; display: flex; flex-direction: column; justify-content: space-evenly; }
.q {
  display: grid; grid-template-columns: 14mm 1fr; gap: 4mm;
  padding: 3mm 0;
}
.q + .q { border-top: 1px solid var(--line); }
.q .num {
  font-family: 'PT Serif', serif; font-weight: 700; font-style: italic;
  font-size: 26pt; line-height: 1; color: var(--accent);
  letter-spacing: -1pt;
  text-shadow: 0 1px 12px rgba(0,0,0,0.4);
}
.q .body { display: flex; flex-direction: column; gap: 1.8mm; }
.q .question {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 12pt; line-height: 1.25; color: var(--text);
  text-shadow: 0 1px 14px rgba(0,0,0,0.5);
}
.q .explain {
  font-size: 10pt; line-height: 1.5; color: rgba(231,226,216,0.92);
  text-shadow: 0 1px 8px rgba(0,0,0,0.35);
}
.q .flag {
  font-size: 9.5pt; line-height: 1.45; color: #FFD8C8; font-weight: 500;
  background: rgba(255,90,42,0.18); padding: 2mm 3mm;
  border-radius: 1.5mm; border-left: 2px solid var(--accent);
  margin-top: 1mm;
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


# ── AI-фоны (с reuse) ───────────────────────────────────────────────────────

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
            print(f"[B] = bg-{num}.png reuse ({existing.stat().st_size // 1024} KB)")
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
    total = TOTAL_PAGES

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
            + '<div class="questions">'
            + _render_params(items, start=start)
            + '</div>'
            + '</div>'
            + _foot(page_idx, total)
            + '</div>'
        )
        content_pages.append(page)

    cta_idx = total  # последняя страница
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
    page_cta = (
        _page_open(cta_idx, bgs)
        + _brand_strip(f"Чек-лист · {cta_idx:02d} / {total:02d}")
        + '<div class="cta-body">' + cta_card + '</div>'
        + _foot(cta_idx, total)
        + '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        '<title>8 параметров оценки офиса класса А</title>'
        f'<style>{CSS}</style></head>'
        f'<body>{page1}{"".join(content_pages)}{page_cta}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "b_office"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[B] → 4 AI-фона (Gemini, reuse если есть)...")
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
