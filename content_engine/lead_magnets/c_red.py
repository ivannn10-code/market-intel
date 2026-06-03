"""Лид-магнит C · «8 red flags при выборе ЖК бизнес-класса» (4 страницы).

Сегмент: покупатели жилья бизнес-класса (для жизни).
Тон: серьёзный, предупреждающий, но без паники. Опытный совет.
Язык: простой, без брокерского жаргона.

Структура:
  1. Обложка
  2. Red flags 1-4 · «До встречи: что видно из рекламы и сайта»
  3. Red flags 5-8 · «На встрече: что говорит «стоп»»
  4. CTA (код РЭД)
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


# ── 8 red flags ─────────────────────────────────────────────────────────────

PARAMS = [
    # Группа 1: До встречи — что видно из рекламы и сайта
    {"q": "«Бизнес-класс» в рекламе, но цена за квадрат на 25-35% ниже соседних ЖК того же сегмента.",
     "e": "Бизнес-класс — это конкретные стандарты: материалы мест общего пользования, отделка квартир, инженерия, паркинг. Если цена ниже на треть, где-то режут: на лифтах, на фасаде, на отделке холлов. Через 3 года это станет видно по сервису и состоянию дома.",
     "f": "Большая скидка к рынку без объяснения = эконом-класс под видом бизнеса. Сравните соседние ЖК того же сегмента и года ввода."},
    {"q": "У застройщика только эконом за плечами — первый объект бизнес-класса.",
     "e": "Бизнес-класс требует другой компетенции, чем эконом: материалы, инженерия, контроль качества подрядчиков, сервис управляющей компании. Минимум 5 лет работы в бизнес-классе и хотя бы 3 сданных объекта — норма для надёжности.",
     "f": "«Мы решили выйти в бизнес-класс» — будут косяки в шумоизоляции, отделке мест общего пользования, сервисе. Это норма для первого проекта."},
    {"q": "На сайте только рендеры. Нет фотографий реальных сданных объектов.",
     "e": "Реальные фото жилых корпусов, лобби, дворовой территории сданных объектов должны быть на сайте. Отзывы реальных жильцов проверяются в открытых источниках: Telegram-каналы ЖК, форумы, Яндекс.Карты.",
     "f": "Только красивые 3D-рендеры и обещания = либо первый проект, либо реальный объект «не дотягивает» до рекламной картинки."},
    {"q": "Сроки сдачи — общие («1 квартал 2027») без конкретного месяца и без обоснования.",
     "e": "В бизнес-классе нормальный застройщик называет конкретный месяц + объясняет, на чём срок основан: готовность подрядчиков, разрешения, этапы. История сдач предыдущих объектов проверяется в ЕИСЖС (наш.дом.рф) — публично, бесплатно.",
     "f": "«Сдадим к концу 2027» без конкретики — закладывайте 6-12 месяцев на срыв в свои планы."},
    # Группа 2: На встрече — что говорит «стоп»
    {"q": "Встреча проходит в офисе продаж, шоурума с реальной отделкой нет.",
     "e": "В бизнес-классе принято показывать шоурум: квартиру с готовой отделкой, материалами мест общего пользования, демонстрационными объектами инженерии. Шоурум — это инвестиция застройщика в доверие покупателя. Если её нет, экономят и на впечатлении, и на реальном качестве.",
     "f": "«Шоурум планируется» к моменту вашего входа на стадии активных продаж — серьёзный сигнал, что застройщик не готов показать товар лицом."},
    {"q": "Менеджер не отвечает конкретно на вопросы про эскроу-счета.",
     "e": "По закону 214-ФЗ деньги покупателя обязаны храниться на эскроу-счетах банка с проектным финансированием. Менеджер должен назвать: конкретный банк (желательно из ТОП-10), процент покрытия стройки проектным финансированием, дату открытия эскроу.",
     "f": "«Эскроу есть, не волнуйтесь» без конкретики или «банк уточним позже» = либо ещё не открыто, либо банк проблемный. Без эскроу — это уже не ДДУ по закону."},
    {"q": "Документы «вышлем после задатка» — а сейчас «нет с собой».",
     "e": "Все ключевые документы: проектная декларация, разрешение на строительство, выписка ЕГРН на земельный участок, акт согласования — должны быть на встрече или в открытом доступе на сайте застройщика и в ЕИСЖС. До любого задатка вы вправе видеть всё.",
     "f": "«Пришлём после внесения задатка» — обходите. Сначала документы, потом деньги. Иначе вы покупаете кота в мешке."},
    {"q": "«Это уникальное предложение, нужно подписать сегодня — иначе продадут».",
     "e": "Срочность и давление — приём массового эконом-сегмента, не бизнес-класса. Реальный бизнес-класс продаётся в темпе клиента, не застройщика. Нормальные застройщики дают неделю-две на принятие решения и спокойно отвечают на все вопросы.",
     "f": "Давление на скорость + «специальная цена только сегодня» = либо объект плохо продаётся, либо вас раскручивают на эмоциях. Хороший дом не уйдёт за день."},
]

PAGE_TAGS = [
    "До встречи: что видно из рекламы",  # стр. 2 (Q1-Q4)
    "На встрече: что говорит «стоп»",     # стр. 3 (Q5-Q8)
]

ITEMS_PER_PAGE = [4, 4]
TOTAL_PAGES = 4

# AI-фоны: премиум-ЖИЛАЯ эстетика (не коммерция как в B)
BG_HINTS = {
    1: "empty premium master bedroom at dawn, floor-to-ceiling window with blurred park trees and distant city visible, soft natural morning light, polished hardwood floor, minimalist linen bed, no people, no specific recognizable building, premium editorial photography, deep teal-navy tones",
    2: "luxury real estate sales brochure with rendered building images on a dark wooden desk, a magnifying glass and a fountain pen, top-down editorial view, premium documentation aesthetic, soft warm side light, no people",
    3: "empty premium living room with leather sofa, large floor-to-ceiling windows, polished hardwood floor, minimalist abstract art on wall, a single coffee table with contract papers and reading glasses, no people, warm directional light, late afternoon",
    4: "a set of keys on a residential property contract with a fountain pen, eyeglasses, a single warm brass desk lamp at dusk, polished wood surface, contemplative mood, no people, premium aesthetic",
}

META = {
    "tag": "Чек-лист · бесплатно",
    "title": "8 red flags<br>при выборе<br>ЖК бизнес-класса",
    "subtitle": "8 сигналов, после которых я говорю клиенту «нет». Простые наблюдения, которые видно невооружённым глазом — ещё на стадии рекламы и первой встречи. Из 12 лет работы с покупателями квартир бизнес-класса в Москве.",
    "title_anchor_label": "сигналов, после которых я говорю «нет»",
    "title_anchor_num": "8",
    "epigraph": "Лучшая сделка — та, от которой я отговорил клиента.<br>Прибыль не в комиссии. Прибыль в долгих отношениях.<br>Эти 8 сигналов экономят годы.",
}

CTA = {
    "tag": "Решаю задачу клиента — лично",
    "headline": "Хотите проверить ваш ЖК<br>на эти red flags — со мной?",
    "lead": "Пришлите кодовое слово в Telegram, SMS или звонком",
    "code": "РЭД",
    "tg": "@IVAN_SUNSIDE",
    "tg_url": "https://t.me/IVAN_SUNSIDE",
    "phone_display": "+7 (925) 078-80-90",
    "phone_tel": "+79250788090",
    "author_name": "Иван Гладышев",
    "author_meta": "Недвижимость Москвы · 12 лет на рынке",
}

CODE = "РЭД"


# ── CSS (тот же шаблон что B v2, без виньетки) ──────────────────────────────

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
  font-size: 44pt; line-height: 1.04; letter-spacing: -1pt;
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
  color: rgba(231,226,216,0.78); max-width: 60mm; line-height: 1.4;
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


def _generate_backgrounds(out_dir: Path) -> dict[int, str]:
    try:
        from ai_bg import generate_bg, build_bg_prompt, is_available
    except Exception as exc:
        print(f"[C] ai_bg недоступен: {exc}"); return {}
    if not is_available():
        print("[C] GEMINI_API_KEY нет"); return {}
    out_dir.mkdir(parents=True, exist_ok=True)

    def gen_one(num: int, hint: str):
        existing = out_dir / f"bg-{num}.png"
        if existing.exists() and existing.stat().st_size > 50_000:
            print(f"[C] = bg-{num}.png reuse ({existing.stat().st_size // 1024} KB)")
            return num, existing.name
        try:
            path = out_dir / f"bg-{num}.png"
            generate_bg(build_bg_prompt(hint), path)
            print(f"[C] ✓ bg-{num}.png ({path.stat().st_size // 1024} KB)")
            return num, path.name
        except Exception as exc:
            print(f"[C] ✗ bg-{num} failed: {exc}"); return num, None

    result: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(gen_one, n, h) for n, h in BG_HINTS.items()]
        for f in futs:
            n, name = f.result()
            if name:
                result[n] = name
    print(f"[C] AI-фоны: {len(result)}/{len(BG_HINTS)} успешно")
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
        '<title>8 red flags при выборе ЖК бизнес-класса</title>'
        f'<style>{CSS}</style></head>'
        f'<body>{page1}{"".join(content_pages)}{page_cta}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "c_red"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[C] → 4 AI-фона (жилая эстетика, Gemini)...")
    bgs = _generate_backgrounds(out_dir)
    html_path = out_dir / "c_red.html"
    pdf_path = out_dir / "c_red.pdf"
    html_path.write_text(build_html(bgs), encoding="utf-8")
    print(f"[C] HTML записан: {html_path}")
    render_html_to_pdf(html_path, pdf_path)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"[C] ✓ PDF готов: {pdf_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
