"""Лид-магнит A · «12 вопросов застройщику до сделки» (v2: 5 страниц с AI-фонами).

5 страниц A4 портрет, тёмная палитра v4.0 (бирюза + оранжевый + светлый greige):
  1. Обложка (хук + ввод)
  2. Вопросы 1-4 · «Компания и документы»
  3. Вопросы 5-8 · «Стоимость и сервис»
  4. Вопросы 9-12 · «Передача и риски»
  5. CTA (тёмно-бирюзовая карточка с кодом СПИСОК)

На каждой странице — свой AI-фон (Gemini), вариация одной премиум-эстетики
(офис/документы/перо/ключи/закат), overlay-strong для читаемости.
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


# ── Контент 12 вопросов (по 4 в группу) ─────────────────────────────────────

QUESTIONS = [
    # Группа 1: Компания и документы
    {"q": "Сколько лет работает на рынке Москвы — и сколько объектов сдано конкретно в бизнес-классе?",
     "e": "Сегмент бизнес-класса требует другой компетенции, чем эконом: материалы, отделка МОП, инженерия, сервис УК. Минимум 5 лет в нише и хотя бы 3 сданных объекта.",
     "f": "Только эконом за плечами + первый «бизнес-класс» — будут косяки в шумоизоляции и сервисе."},
    {"q": "Покажите акты ввода в эксплуатацию последних 5 объектов с датами по плану и по факту.",
     "e": "Срыв сроков на 3-6 месяцев — норма. Срыв на 12+ месяцев на двух подряд проектах — система.",
     "f": "«Документов на встрече нет, вышлем позже» — проверьте сами в ЕИСЖС (наш.дом.рф)."},
    {"q": "Какой банк держит эскроу-счета и какой процент стройки покрыт проектным финансированием?",
     "e": "ТОП-10 банков по 214-ФЗ — нормальный риск-профиль. Региональный малый банк или непрозрачная структура — риск.",
     "f": "На дату подписания ДДУ эскроу не открыто или у банка отозвана аккредитация — стоп."},
    {"q": "Какая степень готовности дома сегодня — по факту, а не в рекламе?",
     "e": "ЕИСЖС (наш.дом.рф) показывает реальную степень готовности объекта. Сверяйтесь публично, не верьте на слово.",
     "f": "В рекламе «готовность 60%», а на стройке нулевой цикл — обманывают и дальше."},
    # Группа 2: Стоимость и сервис
    {"q": "Что входит в стоимость квартиры — отделка, кладовка, машиноместо, благоустройство, балкон?",
     "e": "В бизнес-классе часто «голые стены без отделки». Парковка и кладовка — отдельные договоры. Машиноместо в бизнес-классе Москвы — от 3-5 млн ₽, в премиум-сегменте — до 7-10 млн.",
     "f": "«Уточним при подписании» — закладывайте к цене квартиры ещё цену машино-места и кладовой."},
    {"q": "На каком этапе известна управляющая компания, кто за ней стоит, какой тариф в ₽/м²?",
     "e": "Аффилированная с застройщиком УК на старте — норма. Тариф 90-180 ₽/м² типичен. Ниже 70 ₽/м² — экономия на сервисе.",
     "f": "Тариф не назван или «определит общее собрание» — будете платить надбавку позже."},
    {"q": "Условия пересчёта стоимости после обмера БТИ — кто компенсирует разницу?",
     "e": "Метраж по ДДУ часто отличается от БТИ на 0,5-2 м². Норма: за плюс доплачиваете вы, за минус возвращает застройщик.",
     "f": "«Доплачивает покупатель» при любом отклонении (включая минус) — заведомо невыгодно."},
    {"q": "ВРИ земельного участка — под многоэтажное жилое строительство? Разрешение на строительство действующее?",
     "e": "Вид разрешённого использования и РНС публично проверяются в ЕИСЖС и Росреестре по адресу участка.",
     "f": "ВРИ «коммерция» с переоформлением «по ходу стройки» — стройка может встать."},
    # Группа 3: Передача и риски
    {"q": "Сроки и условия передачи квартиры: приёмка, штрафы, как фиксируются дефекты?",
     "e": "От ввода дома до подписания акта — до 6 месяцев. За просрочку застройщик платит неустойку (1/300 ставки ЦБ за день для физлиц).",
     "f": "Договор обязывает к «приёмке без замечаний» — невыгодно покупателю."},
    {"q": "Условия переуступки прав по ДДУ до сдачи: процент, согласования, ограничения?",
     "e": "Обычно 1-3% от цены ДДУ за согласование переуступки + сделка только через эскроу того же банка.",
     "f": "«Переуступка только с нашего согласия» без условий — выход зависит от воли застройщика."},
    {"q": "Социальная и транспортная инфраструктура — что застройщик обязан построить и когда?",
     "e": "Школа/детсад/паркинг — отдельные этапы, часто +1-3 года к жилью. Метро/развязки — обещания vs планы города.",
     "f": "Инфраструктура есть в буклете, но в проектной декларации отсутствует — значит, не будет."},
    {"q": "История судов с дольщиками: сколько исков за 3 года, какие выиграны / проиграны / в работе?",
     "e": "Бесплатно проверяется по ИНН застройщика на kad.arbitr.ru. Один-два проигрыша — норма. 20+ исков за 3 года — система.",
     "f": "«У нас не бывает судов» — проверьте сами за 5 минут на сайте арбитражного суда."},
]

PAGE_TAGS = [
    "Компания и документы",     # стр. 2 (Q1-Q4)
    "Стоимость и сервис",       # стр. 3 (Q5-Q8)
    "Передача и риски",         # стр. 4 (Q9-Q12)
]

# AI-фоны: один стиль, 5 вариаций ракурса под каждую страницу
BG_HINTS = {
    1: "minimalist executive office at dawn, large floor-to-ceiling window with blurred Moscow skyline, an architectural blueprint rolled on a dark wooden desk, a single leather portfolio, soft warm directional light, generous negative space, premium editorial photography",
    2: "top-down view of architectural blueprints, technical drawings and a heavy fountain pen on a dark wooden table, papers slightly overlapping, soft side light from the right, premium document workspace, no people",
    3: "luxury contract documents with a heavy fountain pen and a leather portfolio on a dark surface, warm directional light from above, premium business aesthetic, single brass pen lamp in background",
    4: "a set of keys lying on a property contract, eyeglasses, a glass of water on a dark wooden surface in late afternoon golden hour, soft light, mood of completion, no people",
    5: "premium executive desk at dusk with city lights visible through a large window, a closed leather portfolio and a single brass lamp casting warm light, dramatic warm-and-teal tones, contemplative mood",
}

META = {
    "tag": "Чек-лист · бесплатно",
    "title": "12 вопросов\nзастройщику<br>до сделки",
    "subtitle": "Список, который я держу в голове на каждой первой встрече с застройщиком. Без этих вопросов покупать квартиру в новостройке — лотерея, а не сделка.",
    "title_anchor_label": "вопросов до подписания",
    "title_anchor_num": "12",
    "epigraph": "Я проверяю каждого застройщика<br>по этому списку — до сделки.<br>Не из недоверия. Из 12 лет опыта.",
}

CTA = {
    "tag": "Решаю задачу клиента — лично",
    "headline": "Хотите проверить вашего застройщика<br>по этому списку — лично со мной?",
    "lead": "Пришлите кодовое слово в Telegram, SMS или звонком",
    "code": "СПИСОК",
    "tg": "@IVAN_SUNSIDE",
    "tg_url": "https://t.me/IVAN_SUNSIDE",
    "phone_display": "+7 (925) 078-80-90",
    "phone_tel": "+79250788090",
    "author_name": "Иван Гладышев",
    "author_meta": "Недвижимость Москвы · 12 лет на рынке",
}


# ── CSS: тёмная палитра v4.0 + overlay-strong как в карусели ────────────────

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

/* верхняя плашка */
.brand-strip {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 8.5pt; letter-spacing: 1.8pt; text-transform: uppercase;
  color: var(--muted); font-weight: 600;
  padding-bottom: 4mm; border-bottom: 1px solid var(--line);
}
.brand-strip .mark { color: var(--accent); margin-right: 7px; font-size: 11pt; line-height: 0; }

/* подвал */
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


# ── AI-фоны (Gemini) ────────────────────────────────────────────────────────

def _generate_backgrounds(out_dir: Path) -> dict[int, str]:
    """Генерит 5 AI-фонов параллельно. Возвращает {page_num: filename}."""
    try:
        from ai_bg import generate_bg, build_bg_prompt, is_available
    except Exception as exc:
        print(f"[A] ai_bg не доступен: {exc}")
        return {}
    if not is_available():
        print("[A] GEMINI_API_KEY нет — генерим без AI-фонов")
        return {}

    out_dir.mkdir(parents=True, exist_ok=True)

    def gen_one(num: int, hint: str):
        existing = out_dir / f"bg-{num}.png"
        if existing.exists() and existing.stat().st_size > 50_000:
            print(f"[A] = bg-{num}.png exists, reuse ({existing.stat().st_size // 1024} KB)")
            return num, existing.name
        try:
            path = out_dir / f"bg-{num}.png"
            generate_bg(build_bg_prompt(hint), path)
            print(f"[A] ✓ bg-{num}.png ({path.stat().st_size // 1024} KB)")
            return num, path.name
        except Exception as exc:
            print(f"[A] ✗ bg-{num} failed: {exc}")
            return num, None

    result: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(gen_one, n, h) for n, h in BG_HINTS.items()]
        for f in futures:
            n, name = f.result()
            if name:
                result[n] = name
    print(f"[A] AI-фоны: {len(result)}/{len(BG_HINTS)} успешно")
    return result


# ── Сборка HTML ─────────────────────────────────────────────────────────────

def _brand_strip(page_label: str) -> str:
    return (
        '<div class="brand-strip">'
        '<div><span class="mark">✱</span>ИГ · НЕДВИЖИМОСТЬ МОСКВЫ</div>'
        f'<div>{page_label}</div>'
        '</div>'
    )


def _foot(page_num: int, total: int) -> str:
    return (
        '<div class="foot">'
        '<div>Иван Гладышев · Недвижимость Москвы</div>'
        f'<div>Код выдачи · СПИСОК · {page_num:02d} / {total:02d}</div>'
        '</div>'
    )


def _page_open(idx: int, bgs: dict[int, str]) -> str:
    bg = bgs.get(idx)
    style = f' style="background-image:url(\'{bg}\');"' if bg else ""
    return f'<div class="page"{style}>'


def _render_questions(items: list[dict], start: int) -> str:
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

    # Page 1: COVER
    page1 = (
        _page_open(1, bgs)
        + _brand_strip("Чек-лист · 01 / 05")
        + f'<div class="cover-epigraph">{META["epigraph"]}</div>'
        + '<div class="cover-body">'
        + f'<div class="cover-tag">{META["tag"]}</div>'
        + f'<div class="cover-title">{META["title"]}</div>'
        + f'<div class="cover-subtitle">{META["subtitle"]}</div>'
        + '<div class="cover-stat">'
        + f'<span class="v">{META["title_anchor_num"]}</span>'
        + f'<span class="l">{META["title_anchor_label"]}</span>'
        + '</div>'
        + '</div>'
        + _foot(1, total)
        + '</div>'
    )

    # Pages 2-4: CONTENT (4 questions per page)
    content_pages = []
    for i, tag in enumerate(PAGE_TAGS):
        page_idx = 2 + i
        start = i * 4 + 1
        questions = QUESTIONS[i * 4:(i + 1) * 4]
        page = (
            _page_open(page_idx, bgs)
            + _brand_strip(f"Чек-лист · {page_idx:02d} / 05")
            + '<div class="content-body">'
            + f'<div class="content-tag">{tag}</div>'
            + _render_questions(questions, start=start)
            + '</div>'
            + _foot(page_idx, total)
            + '</div>'
        )
        content_pages.append(page)

    # Page 5: CTA
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
        + _brand_strip("Чек-лист · 05 / 05")
        + '<div class="cta-body">' + cta_card + '</div>'
        + _foot(5, total)
        + '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        f'<title>12 вопросов застройщику до сделки</title><style>{CSS}</style></head>'
        f'<body>{page1}{"".join(content_pages)}{page5}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "a_spisok"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[A] → генерю 5 AI-фонов (Gemini, параллельно)...")
    bgs = _generate_backgrounds(out_dir)
    html_path = out_dir / "a_spisok.html"
    pdf_path = out_dir / "a_spisok.pdf"
    html_path.write_text(build_html(bgs), encoding="utf-8")
    print(f"[A] HTML записан: {html_path}")
    render_html_to_pdf(html_path, pdf_path)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"[A] ✓ PDF готов: {pdf_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
