"""Лид-магнит D · «Как считать доходность котлована: 8 правил для инвестора» (4 стр).

Сегмент: инвесторы в жильё (покупка на котловане под перепродажу/аренду).
Тон: расчётный, спокойный. Цифры, формулы, ошибки — без воды.
Язык: простой, без брокерского жаргона.

Структура:
  1. Обложка
  2. Правила 1-4 · «Формула: что вычитать из роста цены»
  3. Правила 5-8 · «Сигналы хорошей котлованной сделки»
  4. CTA (код КОТЛОВАН)
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


# ── 8 правил инвестора в котлован ──────────────────────────────────────────

PARAMS = [
    # Группа 1: Формула — что вычитать из роста цены
    {"q": "Доходность — это разница цены, минус ВСЕ расходы. Не только «купил за X, продам за Y».",
     "e": "Чистая прибыль = (Цена продажи − Цена покупки) − Налог − Комиссия агента − Стоимость денег (упущенный депозит). Если хоть один пункт не учли — реальная доходность будет на 5-10% годовых ниже расчётной.",
     "f": "Считаете только «продам дороже на 30%» — гарантированно ошибётесь. Минимум 4 строки расходов до итоговой цифры."},
    {"q": "Налог 13% — если продаёте раньше 5 лет владения. До истечения этого срока НДФЛ платится с разницы.",
     "e": "Налог рассчитывается с разницы между ценой продажи и ценой покупки (статья 217.1 НК РФ). Если продаёте через 5+ лет — налог 0₽. До 5 лет — 13% от разницы (15% сверх 5 млн ₽ разницы). В Москве срок 3 года действует только при единственном жилье.",
     "f": "Забыли про налог в расчёте — реальная доходность падает на 4-7 процентных пунктов. Это критично, если рост цены и так умеренный."},
    {"q": "Комиссия агента при продаже — 3-5% от цены. Это не «потом разберёмся», это в формулу сразу.",
     "e": "Стандартная комиссия агента-риелтора при продаже квартиры в Москве — 3-5% от цены сделки. Если продаёте сами — без агента — тратите 2-3 месяца, в этот срок упускаете доходность от депозита. Считайте либо комиссию, либо упущенное время.",
     "f": "Расчёт «продам сам, сэкономлю» — обычно даёт +1-2 месяца экспозиции. С учётом депозита 18% это съедает половину «экономии»."},
    {"q": "Упущенная доходность депозита — деньги «заморожены» в эскроу 2-3 года.",
     "e": "Депозит 2026: 16-18% годовых. Деньги в эскроу 2-3 года = упущенные 32-50% за этот срок. Если котлован даёт +30% за 2.5 года — то реальный выигрыш над депозитом близок к нулю. Считайте «дельта над депозитом», не «абсолютный рост цены».",
     "f": "«Котлован выгоднее депозита» по факту не всегда. Сравнивайте чистую прибыль с депозитом за тот же срок — поймёте, есть ли смысл."},
    # Группа 2: Сигналы хорошей котлованной сделки
    {"q": "Локация: метро в шаговой доступности или строящееся, развивающийся район.",
     "e": "Главный источник роста цены — развитие района вокруг. Метро в проекте на ближайшие 3-5 лет, новые дороги, бизнес-кластеры, парки. Без этого цена котлована растёт со скоростью инфляции — это не доходность, это сохранение.",
     "f": "Район «никакой» без планов развития = рост цены 5-8% в год = ниже депозита. Не инвестиция, а сохранение капитала."},
    {"q": "Застройщик: топ-10 по объёму сданного, минимум 5 лет в бизнес-классе.",
     "e": "У надёжного застройщика срыв сроков 3-6 месяцев — норма, 12+ месяцев — редкость. Каждый месяц срыва = упущенный 1.5% годовых от депозита. История сдач — публично на ЕИСЖС (наш.дом.рф).",
     "f": "Застройщик «с нуля» или с историей срывов 12+ мес на двух проектах — закладывайте +6 месяцев к плану и пересчитайте доходность."},
    {"q": "Спрос: вторичка района растёт быстрее общего рынка Москвы.",
     "e": "Сравните рост цен вторички района за последние 2 года с общегородским индексом. Если район растёт быстрее — там есть драйвер. Средняя экспозиция квартиры в районе на продаже — <90 дней. Это сигнал ликвидного спроса.",
     "f": "Вторичка района экспонируется по 6+ месяцев — будете продавать долго, упустите ещё месяцы депозита."},
    {"q": "Цена покупки: дисконт 25-35% к цене готовой квартиры аналога. Меньше — нет смысла.",
     "e": "Нормальный дисконт «котлован vs готовая квартира» в бизнес-классе Москвы 2026 — 25-35%. Это плата за риск, время и неликвидность. Если дисконт <20% — котлован не оправдывает риски, проще купить готовое или вложить в депозит.",
     "f": "«Котлован» с дисконтом 10-15% к аналогам = плохая сделка. Либо застройщик переоценил, либо квартиру невозможно сравнить с рынком (нерыночная локация/планировка)."},
]

PAGE_TAGS = [
    "Формула: что вычитать из роста цены",   # стр. 2 (Q1-Q4)
    "Сигналы хорошей сделки",                 # стр. 3 (Q5-Q8)
]

ITEMS_PER_PAGE = [4, 4]
TOTAL_PAGES = 4

# AI-фоны: эстетика «расчётов и инвестиций» — цифры, документы, котлован
BG_HINTS = {
    1: "panoramic view of a residential construction site at dawn from a high vantage point, tower cranes silhouetted against a misty sky, half-built apartment buildings, blurred skyline, deep teal-navy tones, premium editorial photography, no people, no specific recognizable building",
    2: "calculator, fountain pen and financial papers with handwritten numbers on a dark wooden desk, top-down editorial view, soft warm side light, premium business aesthetic, no people, contemplative mood",
    3: "modern empty premium apartment interior at golden hour, large windows looking out onto a developing city district, polished hardwood floor, no furniture except a single chair, light streaming in, premium real estate aesthetic, no people",
    4: "a set of new apartment keys with a property contract, eyeglasses, a fountain pen and a single brass desk lamp on dark polished wood at dusk, warm contemplative mood, no people, premium aesthetic",
}

META = {
    "tag": "Гайд для инвестора · бесплатно",
    "title": "Как считать<br>доходность<br>котлована",
    "subtitle": "8 простых правил для инвестора в новостройку. Формула, типичные ошибки и сигналы хорошей сделки — на цифрах рынка Москвы 2026. Без брокерского жаргона.",
    "title_anchor_label": "правил расчёта и оценки",
    "title_anchor_num": "8",
    "epigraph": "Половина «выгодных котлованов» — это депозит в 18%,<br>растянутый на три года и упущенный.<br>Эти 8 правил помогут отличить одно от другого.",
}

CTA = {
    "tag": "Решаю задачу капитала — лично",
    "headline": "Посчитаю ваш сценарий<br>по конкретному котловану.",
    "lead": "Пришлите кодовое слово в Telegram, SMS или звонком — пришлю Excel-расчёт по вашему объекту.",
    "code": "КОТЛОВАН",
    "tg": "@IVAN_SUNSIDE",
    "tg_url": "https://t.me/IVAN_SUNSIDE",
    "phone_display": "+7 (925) 078-80-90",
    "phone_tel": "+79250788090",
    "author_name": "Иван Гладышев",
    "author_meta": "Недвижимость Москвы · 12 лет на рынке",
}

CODE = "КОТЛОВАН"


# ── CSS (тот же шаблон что B v2 / C) ────────────────────────────────────────

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

.cover-epigraph {
  margin-top: 16mm; max-width: 130mm; margin-left: auto;
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
  font-size: 50pt; line-height: 1.03; letter-spacing: -1pt;
  color: var(--text); text-shadow: 0 2px 24px rgba(0,0,0,0.55);
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
  color: rgba(231,226,216,0.78); max-width: 55mm; line-height: 1.4;
}

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
  font-size: 26pt; letter-spacing: 2pt; color: var(--accent);
  padding: 3mm 8mm; border: 1.8px solid var(--accent); border-radius: 2.5mm;
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


def _generate_backgrounds(out_dir: Path) -> dict[int, str]:
    try:
        from ai_bg import generate_bg, build_bg_prompt, is_available
    except Exception as exc:
        print(f"[D] ai_bg недоступен: {exc}"); return {}
    if not is_available():
        print("[D] GEMINI_API_KEY нет"); return {}
    out_dir.mkdir(parents=True, exist_ok=True)

    def gen_one(num: int, hint: str):
        existing = out_dir / f"bg-{num}.png"
        if existing.exists() and existing.stat().st_size > 50_000:
            print(f"[D] = bg-{num}.png reuse ({existing.stat().st_size // 1024} KB)")
            return num, existing.name
        try:
            path = out_dir / f"bg-{num}.png"
            generate_bg(build_bg_prompt(hint), path)
            print(f"[D] ✓ bg-{num}.png ({path.stat().st_size // 1024} KB)")
            return num, path.name
        except Exception as exc:
            print(f"[D] ✗ bg-{num} failed: {exc}"); return num, None

    result: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(gen_one, n, h) for n, h in BG_HINTS.items()]
        for f in futs:
            n, name = f.result()
            if name:
                result[n] = name
    print(f"[D] AI-фоны: {len(result)}/{len(BG_HINTS)} успешно")
    return result


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
        + _brand_strip(f"Гайд · 01 / {total:02d}")
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
            + _brand_strip(f"Гайд · {page_idx:02d} / {total:02d}")
            + '<div class="content-body">'
            + f'<div class="content-tag">{tag}</div>'
            + '<div class="questions">'
            + _render_params(items, start=start)
            + '</div></div>'
            + _foot(page_idx, total)
            + '</div>'
        )
        content_pages.append(page)

    cta_idx = total
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
        '</div></div>'
    )
    page_cta = (
        _page_open(cta_idx, bgs)
        + _brand_strip(f"Гайд · {cta_idx:02d} / {total:02d}")
        + '<div class="cta-body">' + cta_card + '</div>'
        + _foot(cta_idx, total)
        + '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        '<title>Как считать доходность котлована</title>'
        f'<style>{CSS}</style></head>'
        f'<body>{page1}{"".join(content_pages)}{page_cta}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "d_kotlovan"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[D] → 4 AI-фона (инвестор-эстетика, Gemini)...")
    bgs = _generate_backgrounds(out_dir)
    html_path = out_dir / "d_kotlovan.html"
    pdf_path = out_dir / "d_kotlovan.pdf"
    html_path.write_text(build_html(bgs), encoding="utf-8")
    print(f"[D] HTML записан: {html_path}")
    render_html_to_pdf(html_path, pdf_path)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"[D] ✓ PDF готов: {pdf_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
