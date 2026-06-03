"""Лид-магнит A · «12 вопросов застройщику до сделки».

Чек-лист 2 страницы A4 портрет в фирстиле v4.0 (greige + бирюза + оранжевый).
Контент опирается на публичные источники: 214-ФЗ, ЕИСЖС (наш.дом.рф), Росреестр,
kad.arbitr.ru (арбитражный суд по ИНН), ставка ЦБ. Никаких названий конкретных ЖК/застройщиков.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from build import render_html_to_pdf


# ── Контент ─────────────────────────────────────────────────────────────────

QUESTIONS = [
    {
        "q": "Сколько лет работает на рынке Москвы — и сколько объектов сдано конкретно в бизнес-классе?",
        "e": "Сегмент бизнес-класса требует другой компетенции, чем эконом: материалы, отделка МОП, инженерия, сервис УК. Минимум 5 лет в нише и хотя бы 3 сданных объекта.",
        "f": "Только эконом за плечами + первый «бизнес-класс» — будут косяки в шумоизоляции, отделке мест общего пользования и сервисе.",
    },
    {
        "q": "Покажите акты ввода в эксплуатацию последних 5 объектов с датами по плану и по факту.",
        "e": "Срыв сроков на 3-6 месяцев — рыночная норма. Срыв на 12+ месяцев на двух подряд проектах — система.",
        "f": "«Документов на встрече нет, вышлем позже» — пометьте красным и проверьте сами в ЕИСЖС (наш.дом.рф).",
    },
    {
        "q": "Какой банк держит эскроу-счета и какой процент стройки покрыт проектным финансированием?",
        "e": "ТОП-10 банков по 214-ФЗ — нормальный риск-профиль. Региональный малый банк или непрозрачная структура — риск.",
        "f": "На дату подписания ДДУ эскроу не открыто или у банка отозвана аккредитация — стоп, не подписывайте.",
    },
    {
        "q": "Какая степень готовности дома сегодня — по факту, а не в рекламе?",
        "e": "ЕИСЖС (наш.дом.рф) показывает реальную степень готовности объекта по застройщику. Сверяйтесь публично, не верьте на слово.",
        "f": "В рекламе «готовность 60%», а на стройке нулевой цикл — обманывают сейчас, обманут и при передаче ключей.",
    },
    {
        "q": "Что входит в стоимость квартиры — отделка, кладовка, машиноместо, благоустройство, балкон?",
        "e": "В бизнес-классе часто «голые стены без отделки». Парковка и кладовка — отдельные договоры, 200-800 тыс ₽ за машиноместо.",
        "f": "«Уточним при подписании» — закладывайте +10-30% к рекламной цене на доп-опции.",
    },
    {
        "q": "На каком этапе известна управляющая компания, кто за ней стоит, какой тариф в ₽/м²?",
        "e": "Аффилированная с застройщиком УК на старте — норма для бизнес-класса. Тариф 90-180 ₽/м² типичен. Ниже 70 ₽/м² — экономия на сервисе.",
        "f": "Тариф не назван или «определит общее собрание» — будете платить надбавку через год после заезда.",
    },
    {
        "q": "Условия пересчёта стоимости после обмера БТИ — кто компенсирует разницу?",
        "e": "Метраж по ДДУ часто отличается от БТИ на 0,5-2 м². Норма: за плюс доплачиваете вы, за минус возвращает застройщик.",
        "f": "В договоре «доплачивает покупатель» при любом отклонении (включая минус) — заведомо невыгодная формулировка.",
    },
    {
        "q": "ВРИ земельного участка — под многоэтажное жилое строительство? Разрешение на строительство действующее?",
        "e": "Вид разрешённого использования и РНС публично проверяются в ЕИСЖС и Росреестре по адресу участка.",
        "f": "ВРИ «коммерция» с переоформлением «по ходу стройки» — приостановка строительства возможна на любой стадии.",
    },
    {
        "q": "Сроки и условия передачи квартиры: приёмка, штрафы, как фиксируются дефекты?",
        "e": "От ввода дома до подписания акта — обычно до 6 месяцев. За просрочку застройщик платит неустойку (1/300 ставки ЦБ за день для физлиц).",
        "f": "Договор обязывает к «приёмке без замечаний» или ограничивает срок устранения дефектов 30 днями — невыгодно покупателю.",
    },
    {
        "q": "Условия переуступки прав по ДДУ до сдачи: процент, согласования, ограничения?",
        "e": "Обычно 1-3% от цены ДДУ за согласование переуступки + сделка только через эскроу того же банка.",
        "f": "«Переуступка только с нашего согласия» без чётких условий — ваш выход из объекта зависит от воли застройщика.",
    },
    {
        "q": "Социальная и транспортная инфраструктура — что застройщик обязан построить и когда?",
        "e": "Школа/детсад/паркинг — отдельные этапы, часто +1-3 года к жилью. Метро/развязки — обещания vs реальные планы города.",
        "f": "Инфраструктура есть в рекламном буклете, но в проектной декларации отсутствует — значит, не будет.",
    },
    {
        "q": "История судов с дольщиками: сколько исков за 3 года, какие выиграны / проиграны / в работе?",
        "e": "Бесплатно проверяется по ИНН застройщика на kad.arbitr.ru. Один-два проигрыша — норма. 20+ исков за 3 года — система проблем.",
        "f": "«У нас не бывает судов» — проверьте сами за 5 минут на сайте арбитражного суда.",
    },
]

CTA = {
    "headline": "Хотите проверить вашего застройщика<br>по этому списку — лично со мной?",
    "lead": "Пришлите кодовое слово",
    "code": "СПИСОК",
    "where": "в Telegram, SMS или звонком",
    "tg": "@IVAN_SUNSIDE",
    "tg_url": "https://t.me/IVAN_SUNSIDE",
    "phone_display": "+7 (925) 078-80-90",
    "phone_tel": "+79250788090",
    "signature": "Иван Гладышев · Недвижимость Москвы · 12 лет на рынке",
}

META = {
    "tag": "Чек-лист · бесплатно",
    "title": "12 вопросов\nзастройщику<br>до сделки",
    "subtitle": "Список, который я держу в голове на каждой первой встрече с застройщиком. Без этих вопросов покупать квартиру в новостройке — лотерея, а не сделка.",
}


# ── CSS фирстиля v4.0 для A4-документа ──────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&display=swap');
@page { size: A4 portrait; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
:root {
  --bg: #E7E2D8;
  --ink: #1A1F26;
  --teal: #0F3D4A;
  --accent: #FF5A2A;
  --steel: #4A6A7B;
  --muted: rgba(15,61,74,0.55);
}
html, body { background: var(--bg); color: var(--ink); font-family: 'Inter', sans-serif; -webkit-font-smoothing: antialiased; }
.page { width: 210mm; min-height: 297mm; padding: 18mm 18mm 14mm 18mm; position: relative; background: var(--bg); }
.page + .page { page-break-before: always; }

/* верхняя плашка */
.brand-strip {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 8.5pt; letter-spacing: 1.8pt; text-transform: uppercase;
  color: var(--steel); font-weight: 600;
  padding-bottom: 4mm; border-bottom: 1px solid rgba(74,106,123,0.22);
}
.brand-strip .mark { color: var(--accent); margin-right: 6px; font-size: 11pt; line-height: 0; }

/* hero */
.tag {
  display: inline-block; margin-top: 13mm;
  font-size: 9.5pt; letter-spacing: 2.2pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600;
  border-left: 3px solid var(--accent); padding: 3px 0 3px 11px;
}
.title {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 38pt; line-height: 1.04; letter-spacing: -0.8pt;
  color: var(--teal); margin-top: 7mm; white-space: pre-line;
}
.subtitle {
  font-size: 11.5pt; line-height: 1.5; color: var(--steel);
  margin-top: 6mm; max-width: 150mm;
}
.hr-accent { width: 100%; height: 1px; background: var(--accent); margin: 8mm 0 4mm 0; }

/* вопросы */
.q { display: grid; grid-template-columns: 16mm 1fr; gap: 4mm; padding: 5mm 0 5mm 0; border-bottom: 1px solid rgba(74,106,123,0.16); }
.q:last-child { border-bottom: none; }
.q .num {
  font-family: 'PT Serif', serif; font-weight: 700; font-style: italic;
  font-size: 30pt; line-height: 0.95; color: var(--accent);
  letter-spacing: -1pt;
}
.q .body { display: flex; flex-direction: column; gap: 2.2mm; }
.q .question {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 13pt; line-height: 1.25; color: var(--teal);
}
.q .explain { font-size: 10.2pt; line-height: 1.5; color: var(--ink); }
.q .flag {
  font-size: 9.8pt; line-height: 1.45; color: var(--accent); font-weight: 500;
  background: rgba(255,90,42,0.07); padding: 2.5mm 3mm; border-radius: 2mm;
  border-left: 2px solid var(--accent);
}

/* подвал */
.foot {
  position: absolute; left: 18mm; right: 18mm; bottom: 8mm;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 8pt; letter-spacing: 0.8pt; text-transform: uppercase;
  color: var(--muted); font-weight: 600;
}

/* CTA-карточка */
.cta {
  margin-top: 7mm;
  background: var(--teal); color: var(--bg);
  border-radius: 5mm; padding: 10mm 11mm 9mm 11mm;
  position: relative; overflow: hidden;
}
.cta::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: 5mm; background: var(--accent);
}
.cta-tag {
  font-size: 8.5pt; letter-spacing: 2.4pt; text-transform: uppercase;
  color: var(--accent); font-weight: 600; padding-left: 2mm;
}
.cta-headline {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 19pt; line-height: 1.22; margin-top: 3mm; padding-left: 2mm;
}
.cta-lead {
  font-size: 10.5pt; line-height: 1.5; margin-top: 5mm; padding-left: 2mm;
  color: rgba(231,226,216,0.85);
}
.cta-code-row { margin-top: 3mm; padding-left: 2mm; display: flex; align-items: baseline; gap: 4mm; }
.cta-code {
  font-family: 'PT Serif', serif; font-weight: 700;
  font-size: 24pt; letter-spacing: 2pt; color: var(--accent);
  padding: 2mm 6mm; border: 1.5px solid var(--accent); border-radius: 2mm;
}
.cta-where { font-size: 10pt; color: rgba(231,226,216,0.78); }
.cta-contacts { margin-top: 6mm; padding-left: 2mm; font-size: 10.5pt; line-height: 1.7; }
.cta-contacts a { color: var(--accent); text-decoration: none; font-weight: 600; }
.cta-contacts .label { color: rgba(231,226,216,0.65); margin-right: 4mm; text-transform: uppercase; letter-spacing: 1pt; font-size: 8.5pt; font-weight: 600; }
.cta-sig {
  margin-top: 7mm; padding-left: 2mm; font-size: 8.5pt;
  color: rgba(231,226,216,0.62); letter-spacing: 0.8pt; text-transform: uppercase; font-weight: 500;
}
"""


# ── Сборка HTML ─────────────────────────────────────────────────────────────

def _render_questions(items: list[dict], start: int) -> str:
    out = []
    for i, q in enumerate(items, start=start):
        out.append(
            f'<div class="q">'
            f'<div class="num">{i:02d}</div>'
            f'<div class="body">'
            f'<div class="question">{q["q"]}</div>'
            f'<div class="explain">{q["e"]}</div>'
            f'<div class="flag">🚩 {q["f"]}</div>'
            f'</div></div>'
        )
    return "".join(out)


def build_html() -> str:
    page1_qs = QUESTIONS[:6]
    page2_qs = QUESTIONS[6:]

    page1 = (
        '<div class="page">'
        '<div class="brand-strip">'
        '<div><span class="mark">✱</span>ИГ · НЕДВИЖИМОСТЬ МОСКВЫ</div>'
        '<div>Чек-лист · 01 / 02</div>'
        '</div>'
        f'<div class="tag">{META["tag"]}</div>'
        f'<div class="title">{META["title"]}</div>'
        f'<div class="subtitle">{META["subtitle"]}</div>'
        '<div class="hr-accent"></div>'
        f'{_render_questions(page1_qs, start=1)}'
        '<div class="foot"><div>Иван Гладышев · Недвижимость Москвы</div><div>Код выдачи · СПИСОК</div></div>'
        '</div>'
    )

    cta_block = (
        '<div class="cta">'
        '<div class="cta-tag">Решаю задачу клиента — лично</div>'
        f'<div class="cta-headline">{CTA["headline"]}</div>'
        f'<div class="cta-lead">{CTA["lead"]}</div>'
        '<div class="cta-code-row">'
        f'<div class="cta-code">{CTA["code"]}</div>'
        f'<div class="cta-where">{CTA["where"]}</div>'
        '</div>'
        '<div class="cta-contacts">'
        f'<div><span class="label">Telegram</span><a href="{CTA["tg_url"]}">{CTA["tg"]}</a></div>'
        f'<div><span class="label">Звонок / SMS</span><a href="tel:{CTA["phone_tel"]}">{CTA["phone_display"]}</a></div>'
        '</div>'
        f'<div class="cta-sig">{CTA["signature"]}</div>'
        '</div>'
    )

    page2 = (
        '<div class="page">'
        '<div class="brand-strip">'
        '<div><span class="mark">✱</span>ИГ · НЕДВИЖИМОСТЬ МОСКВЫ</div>'
        '<div>Чек-лист · 02 / 02</div>'
        '</div>'
        '<div style="margin-top:8mm;"></div>'
        f'{_render_questions(page2_qs, start=7)}'
        f'{cta_block}'
        '<div class="foot"><div>Иван Гладышев · Недвижимость Москвы</div><div>Код выдачи · СПИСОК</div></div>'
        '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'
        f'<title>12 вопросов застройщику до сделки</title><style>{CSS}</style></head>'
        f'<body>{page1}{page2}</body></html>'
    )


def main() -> int:
    out_dir = HERE / "a_spisok"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "a_spisok.html"
    pdf_path = out_dir / "a_spisok.pdf"
    html_path.write_text(build_html(), encoding="utf-8")
    print(f"[A] HTML записан: {html_path}")
    render_html_to_pdf(html_path, pdf_path)
    size_kb = pdf_path.stat().st_size // 1024
    print(f"[A] ✓ PDF готов: {pdf_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
