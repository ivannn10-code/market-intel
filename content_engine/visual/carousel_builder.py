"""Генератор каруселей: тема → Claude генерит структуру слайдов → AI-фоны (Gemini)
→ HTML (фирстиль v2) → PNG (Playwright).

Пайплайн:
  1. propose_topics(facts)           — Claude предлагает 3 темы из свежих фактов рынка
  2. generate_carousel_content(...)  — Claude через tool_use возвращает структуру слайдов
     (hero + 4-6 content-слайдов с layout: data/points/compare/text + cta), у каждого
     слайда есть bg_hint — короткое описание AI-фона.
  3. build_carousel(content, out_dir) — генерит AI-фоны (Gemini, concurrent, с fallback),
     собирает HTML по фирстилю v2, рендерит в PNG.
  4. caption_md(content)             — подпись + хэштеги + первый коммент.

Фирстиль v2 (эталон — .business/content/carousels/.../v2): каждый слайд = постановочный
фото-кадр (AI-фон) + typographic overlay. Контент прижат вниз (hero) или центрирован
(content) — НИКАКИХ пустых пространств посередине. Палитра графит/слоновая кость/терракота,
PT Serif + Inter, 1080×1350.
"""

from __future__ import annotations

import concurrent.futures
import re
import sys
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
# content_engine/ — чтобы импортировать редакцию агентов
_CE = HERE.parent
if str(_CE) not in sys.path:
    sys.path.insert(0, str(_CE))
try:
    import agent_team  # редакция агентов (бриф + факт-чек + вычитка)
except Exception:
    agent_team = None

# ── Фирстиль v2 (inline CSS, Google Fonts CDN) ───────────────────────────────
SLIDE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&display=swap');
:root{--bg:#14171C;--text:#F4F1EA;--accent:#B85C3C;--muted:#8A857B;--watermark:rgba(244,241,234,0.55);}
*{margin:0;padding:0;box-sizing:border-box;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}
html,body{width:1080px;height:1350px;overflow:hidden;background:var(--bg);}
.slide{width:1080px;height:1350px;background:var(--bg);background-size:cover;background-position:center;
  background-repeat:no-repeat;color:var(--text);position:relative;font-family:'Inter',sans-serif;}
/* fallback-фон, если AI-картинки нет — графит с мягким терракотовым свечением */
.slide.no-bg{background:
  radial-gradient(120% 90% at 78% 18%, rgba(184,92,60,0.28) 0%, rgba(184,92,60,0) 55%),
  radial-gradient(90% 70% at 12% 88%, rgba(244,241,234,0.06) 0%, rgba(244,241,234,0) 60%),
  linear-gradient(160deg, #1A1E24 0%, #14171C 60%, #101216 100%);}
.slide::before{content:'';position:absolute;inset:0;z-index:1;}
.slide.overlay-bottom::before{background:linear-gradient(180deg,
  rgba(20,23,28,0.40) 0%,rgba(20,23,28,0.15) 24%,rgba(20,23,28,0.22) 50%,
  rgba(20,23,28,0.86) 86%,rgba(20,23,28,0.96) 100%);}
.slide.overlay-strong::before{background:linear-gradient(180deg,
  rgba(20,23,28,0.93) 0%,rgba(20,23,28,0.74) 38%,rgba(20,23,28,0.62) 68%,rgba(20,23,28,0.92) 100%);}
.slide.overlay-cta::before{background:linear-gradient(135deg,
  rgba(184,92,60,0.90) 0%,rgba(146,70,45,0.78) 48%,rgba(20,23,28,0.70) 100%);}
.slide-content{position:relative;z-index:2;width:100%;height:100%;padding:70px 72px 80px;
  display:flex;flex-direction:column;}
/* верхний ряд */
.top-row{display:flex;justify-content:space-between;align-items:center;width:100%;}
.watermark{font-weight:600;font-size:22px;letter-spacing:3.6px;text-transform:uppercase;
  color:var(--watermark);display:flex;align-items:center;gap:14px;}
.watermark .mark{color:var(--accent);font-size:28px;line-height:0;margin-top:4px;}
.pager-pill{font-family:'PT Serif',serif;font-weight:700;font-size:24px;letter-spacing:0.8px;color:var(--text);
  background:rgba(20,23,28,0.70);border:1px solid rgba(244,241,234,0.25);border-radius:100px;
  padding:12px 28px;backdrop-filter:blur(8px);}
/* огромная полупрозрачная цифра слайда */
.huge-num{position:absolute;bottom:26px;right:48px;font-family:'PT Serif',serif;font-weight:700;
  font-style:italic;font-size:220px;line-height:0.85;letter-spacing:-8px;color:rgba(244,241,234,0.08);
  z-index:2;user-select:none;pointer-events:none;}
.slide.overlay-cta .huge-num{color:rgba(244,241,234,0.14);}
/* мини-тег */
.mini-tag{font-weight:600;font-size:20px;letter-spacing:3.4px;text-transform:uppercase;color:var(--accent);
  display:inline-flex;align-items:center;border-left:3px solid var(--accent);padding:8px 0 8px 20px;}
.slide.overlay-cta .mini-tag{color:var(--text);border-left-color:var(--text);}
.slide.overlay-cta .watermark,.slide.overlay-cta .watermark .mark{color:rgba(244,241,234,0.78);}
/* HERO */
.hero-quote-section{margin-top:54px;max-width:480px;margin-left:auto;text-align:right;}
.hero-quote{font-family:'PT Serif',serif;font-style:italic;font-size:32px;line-height:1.3;color:var(--accent);}
.hero-body{flex:1;display:flex;flex-direction:column;justify-content:flex-end;padding-bottom:22px;}
.hero-tag-row{margin-bottom:72px;}
.hero-headline{font-family:'PT Serif',serif;font-weight:700;font-size:80px;line-height:1.03;
  letter-spacing:-1.8px;color:var(--text);max-width:940px;text-shadow:0 2px 30px rgba(0,0,0,0.45);}
.hero-headline .accent{color:var(--accent);}
.hero-headline em{font-style:italic;font-weight:400;color:rgba(244,241,234,0.78);}
.hero-stat{margin-top:30px;display:inline-flex;align-items:baseline;gap:18px;}
.hero-stat .v{font-family:'PT Serif',serif;font-weight:700;font-size:64px;color:var(--accent);line-height:1;}
.hero-stat .l{font-size:20px;letter-spacing:1.5px;text-transform:uppercase;color:rgba(244,241,234,0.7);}
/* CONTENT (слайды 2..n-1) */
.content-body{flex:1;display:flex;flex-direction:column;justify-content:center;padding:20px 0;}
.content-tag-row{margin-bottom:22px;}
.section-label{font-family:'PT Serif',serif;font-weight:700;font-size:54px;line-height:1.04;
  letter-spacing:-1.4px;color:var(--text);margin-bottom:40px;text-shadow:0 2px 24px rgba(0,0,0,0.4);}
.section-label .accent{color:var(--accent);}
/* data: строки label ↔ value */
.calc-rows{display:flex;flex-direction:column;}
.calc-row{display:flex;align-items:baseline;justify-content:space-between;gap:28px;padding:22px 0;
  border-bottom:1px solid rgba(244,241,234,0.16);}
.calc-row:last-child{border-bottom:none;}
.calc-label{font-size:27px;line-height:1.32;color:var(--text);flex:1;}
.calc-label .muted{display:block;color:rgba(244,241,234,0.55);font-size:18px;margin-top:6px;}
.calc-value{font-family:'PT Serif',serif;font-weight:700;font-size:46px;color:var(--accent);white-space:nowrap;}
.calc-final{margin-top:30px;padding-top:26px;border-top:2px solid var(--accent);}
.calc-final-label{font-weight:600;font-size:17px;letter-spacing:2.4px;text-transform:uppercase;
  color:rgba(244,241,234,0.72);margin-bottom:12px;}
.calc-final-value{font-family:'PT Serif',serif;font-weight:700;font-style:italic;font-size:80px;
  line-height:1;letter-spacing:-2.5px;color:var(--accent);}
.calc-final-formula{font-size:20px;color:rgba(244,241,234,0.65);margin-top:14px;line-height:1.4;}
/* points: нумерованный список */
.break-points{display:flex;flex-direction:column;gap:26px;}
.break-point{display:flex;align-items:flex-start;gap:26px;padding-bottom:24px;
  border-bottom:1px solid rgba(244,241,234,0.16);}
.break-point:last-child{border-bottom:none;}
.break-num{font-family:'PT Serif',serif;font-weight:700;font-style:italic;font-size:52px;line-height:1;
  color:var(--accent);flex-shrink:0;width:64px;}
.break-text{font-size:28px;line-height:1.4;color:var(--text);}
.break-text strong{font-weight:600;color:var(--accent);}
/* compare: две колонки */
.compare-grid{display:grid;grid-template-columns:1fr 1px 1fr;gap:36px;align-items:stretch;margin-top:6px;}
.compare-col{display:flex;flex-direction:column;align-items:flex-start;gap:16px;}
.compare-divider{width:1px;background:rgba(184,92,60,0.55);}
.compare-tag{font-weight:600;font-size:18px;letter-spacing:3px;text-transform:uppercase;
  color:rgba(244,241,234,0.78);}
.compare-value{font-family:'PT Serif',serif;font-weight:700;font-style:italic;font-size:68px;
  line-height:0.96;letter-spacing:-2px;color:var(--accent);}
.compare-formula{font-size:21px;line-height:1.4;color:rgba(244,241,234,0.72);}
.compare-summary{margin-top:40px;padding-top:24px;border-top:1px solid rgba(244,241,234,0.18);
  font-weight:500;font-size:26px;line-height:1.4;color:var(--text);}
.compare-summary .accent{color:var(--accent);font-weight:600;}
/* text: абзацы */
.paragraphs{display:flex;flex-direction:column;gap:28px;}
.para{font-size:30px;line-height:1.45;color:var(--text);text-shadow:0 1px 16px rgba(0,0,0,0.35);}
.para .accent{font-weight:600;color:var(--accent);}
.para strong{font-weight:600;}
/* footnote-источники */
.content-footer{font-size:16px;line-height:1.4;color:rgba(244,241,234,0.55);max-width:80%;margin-top:34px;}
/* CTA */
.cta-body{flex:1;display:flex;flex-direction:column;justify-content:space-between;padding-top:60px;}
.cta-tag-row{margin-bottom:24px;}
.cta-headline{font-family:'PT Serif',serif;font-weight:700;font-size:90px;line-height:0.99;
  letter-spacing:-2.5px;color:var(--text);max-width:760px;}
.cta-sub{font-size:30px;line-height:1.45;color:var(--text);margin-top:34px;max-width:760px;}
.cta-sub .codeword{font-family:'PT Serif',serif;font-weight:700;font-style:italic;color:var(--text);
  background:rgba(20,23,28,0.55);padding:2px 14px;border-radius:4px;letter-spacing:1px;}
.cta-footer{display:flex;align-items:flex-end;justify-content:space-between;padding-top:44px;
  margin-top:44px;border-top:1px solid rgba(244,241,234,0.35);}
.cta-author-name{font-family:'PT Serif',serif;font-weight:700;font-size:30px;color:var(--text);}
.cta-author-meta{font-size:17px;letter-spacing:0.6px;color:rgba(244,241,234,0.85);margin-top:6px;}
.cta-handle{font-weight:600;font-size:22px;letter-spacing:0.8px;color:var(--text);
  background:rgba(20,23,28,0.55);border:1px solid rgba(244,241,234,0.35);border-radius:100px;padding:10px 22px;}
"""


def _doc(slide_class: str, bg_file: str | None, inner: str, huge: str) -> str:
    style_bg = f" style=\"background-image:url('{bg_file}');\"" if bg_file else ""
    cls = slide_class if bg_file else f"{slide_class} no-bg"
    return (
        f'<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><style>{SLIDE_CSS}</style></head>'
        f'<body><div class="slide {cls}"{style_bg}>'
        f'<div class="slide-content">{inner}</div>'
        f'<div class="huge-num">{huge}</div></div></body></html>'
    )


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(s: str) -> str:
    """*слово* → терракота (.accent), _слово_ → приглушённый курсив (<em>)."""
    out = esc(s)
    out = re.sub(r"\*(.+?)\*", r'<span class="accent">\1</span>', out)
    out = re.sub(r"_(.+?)_", r"<em>\1</em>", out)
    return out


def _top_row(idx: int, total: int) -> str:
    return (
        '<div class="top-row">'
        '<div class="watermark"><span class="mark">✱</span><span>ИГ · Недвижимость Москвы</span></div>'
        f'<div class="pager-pill">{idx:02d} / {total:02d}</div></div>'
    )


def _mini_tag(text: str) -> str:
    return f'<span class="mini-tag">{esc(text)}</span>' if text else ""


# ── Сборка слайдов ───────────────────────────────────────────────────────────

def slide_hero(idx: int, total: int, h: dict, bg_file: str | None) -> str:
    quote = ""
    if h.get("quote"):
        quote = f'<div class="hero-quote-section"><div class="hero-quote">{fmt(h["quote"])}</div></div>'
    stat = ""
    st = h.get("stat") or {}
    if st.get("value"):
        stat = (f'<div class="hero-stat"><span class="v">{esc(st["value"])}</span>'
                f'<span class="l">{esc(st.get("label",""))}</span></div>')
    inner = (
        _top_row(idx, total)
        + quote
        + '<div class="hero-body">'
        + f'<div class="hero-tag-row">{_mini_tag(h.get("label",""))}</div>'
        + f'<div class="hero-headline">{fmt(h["title"])}</div>'
        + stat
        + '</div>'
    )
    return _doc("overlay-bottom", bg_file, inner, f"{idx:02d}")


def _layout_data(s: dict) -> str:
    rows = []
    for r in s.get("rows", []):
        sub = f'<span class="muted">{fmt(r["sub"])}</span>' if r.get("sub") else ""
        rows.append(
            f'<div class="calc-row"><div class="calc-label">{fmt(r.get("label",""))}{sub}</div>'
            f'<div class="calc-value">{fmt(r.get("value",""))}</div></div>'
        )
    block = f'<div class="calc-rows">{"".join(rows)}</div>'
    fin = s.get("final") or {}
    if fin.get("value"):
        formula = f'<div class="calc-final-formula">{fmt(fin["formula"])}</div>' if fin.get("formula") else ""
        block += (f'<div class="calc-final"><div class="calc-final-label">{esc(fin.get("label",""))}</div>'
                  f'<div class="calc-final-value">{fmt(fin["value"])}</div>{formula}</div>')
    return block


def _layout_points(s: dict) -> str:
    items = []
    for i, p in enumerate(s.get("points", []), 1):
        if isinstance(p, dict):
            strong = f'<strong>{fmt(p["strong"])}. </strong>' if p.get("strong") else ""
            text = fmt(p.get("text", ""))
        else:
            strong, text = "", fmt(str(p))
        items.append(f'<div class="break-point"><div class="break-num">{i:02d}</div>'
                     f'<div class="break-text">{strong}{text}</div></div>')
    return f'<div class="break-points">{"".join(items)}</div>'


def _layout_compare(s: dict) -> str:
    def col(c: dict) -> str:
        formula = f'<div class="compare-formula">{fmt(c["formula"])}</div>' if c.get("formula") else ""
        return (f'<div class="compare-col"><div class="compare-tag">{esc(c.get("tag",""))}</div>'
                f'<div class="compare-value">{fmt(c.get("value",""))}</div>{formula}</div>')
    left = col(s.get("left", {}))
    right = col(s.get("right", {}))
    summary = f'<div class="compare-summary">{fmt(s["summary"])}</div>' if s.get("summary") else ""
    return f'<div class="compare-grid">{left}<div class="compare-divider"></div>{right}</div>{summary}'


def _layout_text(s: dict) -> str:
    paras = "".join(f'<div class="para">{fmt(p)}</div>' for p in s.get("paragraphs", []))
    return f'<div class="paragraphs">{paras}</div>'


_LAYOUTS = {"data": _layout_data, "points": _layout_points, "compare": _layout_compare, "text": _layout_text}


def slide_content(idx: int, total: int, s: dict, bg_file: str | None) -> str:
    layout = s.get("layout", "text")
    body = _LAYOUTS.get(layout, _layout_text)(s)
    footer = f'<div class="content-footer">{esc(s["footnote"])}</div>' if s.get("footnote") else ""
    inner = (
        _top_row(idx, total)
        + '<div class="content-body">'
        + f'<div class="content-tag-row">{_mini_tag(s.get("tag",""))}</div>'
        + f'<div class="section-label">{fmt(s.get("title",""))}</div>'
        + body + footer
        + '</div>'
    )
    return _doc("overlay-strong", bg_file, inner, f"{idx:02d}")


def slide_cta(idx: int, total: int, cta: dict, bg_file: str | None) -> str:
    sub = fmt(cta.get("sub", ""))
    if cta.get("codeword"):
        sub = sub.replace(esc(cta["codeword"]), f'<span class="codeword">{esc(cta["codeword"])}</span>')
    inner = (
        _top_row(idx, total)
        + '<div class="cta-body">'
        + f'<div><div class="cta-tag-row">{_mini_tag(cta.get("label","Решаю задачу капитала"))}</div>'
        + f'<div class="cta-headline">{fmt(cta.get("title",""))}</div>'
        + f'<div class="cta-sub">{sub}</div></div>'
        + '<div class="cta-footer">'
        + '<div><div class="cta-author-name">Иван Гладышев</div>'
        + '<div class="cta-author-meta">Недвижимость Москвы · 12 лет на рынке</div></div>'
        + '<div class="cta-handle">@IVAN_SUNSIDE</div></div>'
        + '</div>'
    )
    return _doc("overlay-cta", bg_file, inner, f"{idx:02d}")


# ── Claude: предложить темы ──────────────────────────────────────────────────
TOPICS_TOOL = {
    "name": "propose_topics",
    "description": "Предложи 3 темы для Instagram-карусели премиум-эксперта по недвижимости Москвы на основе свежих фактов рынка.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array", "minItems": 3, "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Короткое название темы (до 60 знаков)"},
                        "angle": {"type": "string", "description": "Угол подачи в 1 предложении — почему зацепит"},
                        "type": {"type": "string", "enum": ["case", "methodology", "comparison", "red_flags", "checklist", "market"]},
                    },
                    "required": ["title", "angle", "type"],
                },
            }
        },
        "required": ["topics"],
    },
}

TOPICS_SYSTEM = """Ты — контент-стратег премиум-эксперта по недвижимости Москвы (Иван Гладышев, бизнес-класс жильё + коммерция класса А, 12 лет рынка).

Предложи 3 РАЗНЫЕ темы для Instagram-карусели на основе свежих фактов рынка. Карусель = глубокий контент с сохранениями (saves), не однодневка.

Правила:
- Темы под премиум-аудиторию: покупатели бизнес-класса, инвесторы в жильё/коммерцию, бизнес под офис
- Без инфоцыганщины, без кликбейта, без «топ худших ЖК»
- Методология / сравнение / red flags / чек-лист / разбор кейса — форматы которые сохраняют
- Цепляющий, но честный угол подачи
- Опирайся на переданные свежие факты рынка"""


def propose_topics(facts: str, client: anthropic.Anthropic, model: str) -> list[dict]:
    resp = client.messages.create(
        model=model, max_tokens=1500,
        system=TOPICS_SYSTEM,
        tools=[TOPICS_TOOL], tool_choice={"type": "tool", "name": "propose_topics"},
        messages=[{"role": "user", "content": f"Свежие факты рынка:\n\n{facts[:8000]}\n\nПредложи 3 темы карусели."}],
    )
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use":
            return b.input.get("topics", [])
    return []


# ── Claude: сгенерить контент карусели ───────────────────────────────────────
CAROUSEL_TOOL = {
    "name": "build_carousel",
    "description": "Создай структуру Instagram-карусели из hero + 4-6 content-слайдов + cta для премиум-эксперта по недвижимости.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hero": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Мини-тег категории, КАПСОМ, 2-4 слова"},
                    "title": {"type": "string", "description": "Хук-заголовок. *слово* = терракота, _слово_ = приглушённый курсив"},
                    "quote": {"type": "string", "description": "Опционально: короткая цитата-эпиграф (1-3 строки), курсив сверху-справа"},
                    "stat": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}, "value": {"type": "string", "description": "Цифра-якорь, напр '238 млн ₽'"}},
                    },
                    "bg_hint": {"type": "string", "description": "Англ. описание AI-фона: обобщённая премиум-сцена (интерьер/материалы/свет/предметы). БЕЗ реальных зданий, БЕЗ лиц, БЕЗ текста."},
                },
                "required": ["label", "title", "bg_hint"],
            },
            "slides": {
                "type": "array", "minItems": 4, "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {"type": "string", "enum": ["data", "points", "compare", "text"],
                                   "description": "data=строки цифр (label↔value); points=нумерованный список; compare=2 колонки; text=2-3 абзаца"},
                        "tag": {"type": "string", "description": "Мини-тег слайда, КАПСОМ, 2-3 слова"},
                        "title": {"type": "string", "description": "Заголовок слайда (PT Serif). Можно *слово*"},
                        "rows": {"type": "array", "description": "ДЛЯ layout=data: строки цифр",
                                 "items": {"type": "object", "properties": {
                                     "label": {"type": "string"}, "sub": {"type": "string", "description": "Опционально: уточнение мелким"},
                                     "value": {"type": "string", "description": "Значение/цифра (можно *выделить*)"}}}},
                        "final": {"type": "object", "description": "ДЛЯ layout=data: итоговая строка (опц.)",
                                  "properties": {"label": {"type": "string"}, "value": {"type": "string"}, "formula": {"type": "string"}}},
                        "points": {"type": "array", "description": "ДЛЯ layout=points: пункты",
                                   "items": {"type": "object", "properties": {
                                       "strong": {"type": "string", "description": "Опц. жирное начало"}, "text": {"type": "string"}}}},
                        "left": {"type": "object", "description": "ДЛЯ layout=compare: левая колонка",
                                 "properties": {"tag": {"type": "string"}, "value": {"type": "string"}, "formula": {"type": "string"}}},
                        "right": {"type": "object", "description": "ДЛЯ layout=compare: правая колонка",
                                  "properties": {"tag": {"type": "string"}, "value": {"type": "string"}, "formula": {"type": "string"}}},
                        "summary": {"type": "string", "description": "ДЛЯ layout=compare: вывод под колонками"},
                        "paragraphs": {"type": "array", "items": {"type": "string"}, "description": "ДЛЯ layout=text: 2-3 абзаца"},
                        "footnote": {"type": "string", "description": "Опц. строка источников мелким шрифтом"},
                        "bg_hint": {"type": "string", "description": "Англ. описание AI-фона (обобщённая премиум-сцена, БЕЗ зданий/лиц/текста)"},
                    },
                    "required": ["layout", "title", "bg_hint"],
                },
            },
            "cta": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Мини-тег, напр 'Решаю задачу капитала'"},
                    "title": {"type": "string", "description": "CTA-заголовок"},
                    "sub": {"type": "string", "description": "Призыв написать в директ / задать вопрос"},
                    "codeword": {"type": "string", "description": "Опц. кодовое слово для директа (подсветится)"},
                    "bg_hint": {"type": "string", "description": "Англ. описание AI-фона (обобщённая премиум-сцена)"},
                },
                "required": ["title", "sub", "bg_hint"],
            },
            "caption": {"type": "string", "description": "Подпись под публикацией для Instagram (800-1500 знаков, премиум tone of voice)"},
            "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5},
            "first_comment": {"type": "string", "description": "Первый комментарий (провокация/доп-цифра/контраргумент, 200-400 знаков)"},
        },
        "required": ["hero", "slides", "cta", "caption", "hashtags", "first_comment"],
    },
}

CAROUSEL_SYSTEM = """Ты — связка copywriter + carousel-designer премиум-эксперта по недвижимости Москвы (Иван Гладышев, бизнес-класс + коммерция А, 12 лет, 17,5 млрд сделок).

Создаёшь Instagram-карусель по всем законам маркетинга:
- 1-й слайд (hero) — мощный хук, останавливает листание
- средние слайды — раскрытие ценности: факты, цифры, сравнения, методология
- последний (cta) — призыв к действию (написать в директ, задать вопрос)
- драматургия свайпа: каждый слайд тянет к следующему

Tone of voice: экспертный, спокойный, с цифрами. БЕЗ инфоцыганщины, БЕЗ «AI-привкуса», БЕЗ воды.
УТП Ивана: «Я не продаю объекты — подбираю недвижимость под вашу задачу».

ВАЖНО про вёрстку слайдов (чтобы не было пустых пространств):
- Для каждого content-слайда ОБЯЗАТЕЛЬНО выбери layout под содержание:
  · data — когда есть 3-5 цифр/параметров (строки label↔value). Лучший выбор для рыночных данных.
  · points — нумерованный чек-лист / шаги / red flags (3-5 пунктов).
  · compare — сравнение двух вариантов (2 колонки + вывод).
  · text — рассуждение/методология (2-3 коротких абзаца, НЕ один абзац).
- Наполняй слайд достаточно: data → 3-5 строк; points → 3-5 пунктов; text → 2-3 абзаца. Слайд не должен быть полупустым.

Правила текста:
- Слайд = 1 мысль. Короткие фразы. Цифры с источником (footnote).
- *Звёздочками* выделяй 1-2 ключевых слова (терракота). _Подчёркивание_ = приглушённый курсив.
- Опирайся на переданные факты рынка, НЕ выдумывай цифры. Если точной цифры нет — не пиши её.

bg_hint (для каждого слайда) — английское описание AI-фона: ОБОБЩЁННАЯ премиум-сцена
(интерьер бизнес-класса, материалы, утренний свет, предметы: ключи, документы, кофе, чертежи,
вид города в дымке). СТРОГО: без реальных узнаваемых зданий, без лиц людей, без текста на картинке.

caption — премиум-подпись (НЕ дубль слайдов), 800-1500 знаков.
hashtags — ровно 5, премиум-формат (#НедвижимостьМосквы и т.п.).
first_comment — НЕ дубль подписи: провокация / +1 цифра / контраргумент."""


def generate_carousel_content(topic: str, facts: str, client: anthropic.Anthropic, model: str,
                              team: bool = True, progress=None) -> dict | None:
    """Генерит структуру карусели. С team=True редакция агентов делает бриф + факт-чек
    апстрим и вычитывает подпись (carousel-designer + copywriter уже зашиты в CAROUSEL_SYSTEM)."""
    brief_block = ""
    verified = facts
    if team and agent_team is not None:
        try:
            if progress:
                progress("🧭 Маркетолог + факт-чек готовят бриф карусели…")
            brief = agent_team.write_brief(topic, facts, "carousel", "instagram", client)
            verified = agent_team.verify_facts(facts, brief or {}, client) or facts
            brief_block = f"БРИФ ОТ КОМАНДЫ:\n{agent_team._brief_text(brief)}\n\n"
        except Exception as exc:
            print(f"[carousel] team enrich failed: {exc}")

    resp = client.messages.create(
        model=model, max_tokens=5000,
        system=CAROUSEL_SYSTEM,
        tools=[CAROUSEL_TOOL], tool_choice={"type": "tool", "name": "build_carousel"},
        messages=[{"role": "user", "content": (
            f"Тема карусели: «{topic}»\n\n{brief_block}"
            f"ПРОВЕРЕННЫЕ ФАКТЫ (используй только их, с маркерами):\n{verified[:9000]}\n\n"
            f"Создай карусель из hero + 4-6 content-слайдов + cta по правилам. "
            f"У каждого слайда подбери layout под содержание и заполни его данными."
        )}],
    )
    content = None
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use":
            content = b.input
            break
    if not content:
        return None

    # Финальная вычитка подписи редактором (публичный текст под брендом)
    if team and agent_team is not None and content.get("caption"):
        try:
            if progress:
                progress("✅ Редактор вычитывает подпись…")
            edited = agent_team.final_edit(content["caption"], "Instagram carousel caption", client)
            if edited:
                content["caption"] = edited
        except Exception as exc:
            print(f"[carousel] caption edit failed: {exc}")
    return content


# ── AI-фоны ──────────────────────────────────────────────────────────────────

def _gen_one_bg(hint: str, out_png: Path) -> Path | None:
    try:
        from ai_bg import generate_bg, build_bg_prompt
        return generate_bg(build_bg_prompt(hint), out_png)
    except Exception as exc:
        print(f"[carousel] AI-фон не сгенерён ({out_png.name}): {exc}")
        return None


def generate_backgrounds(content: dict, html_dir: Path, progress=None) -> dict[int, str]:
    """Генерит AI-фоны для всех слайдов (concurrent). Возвращает {slide_idx: bg_filename}.
    Если ai_bg недоступен или ключа нет — возвращает пустой dict (слайды отрендерятся с no-bg)."""
    try:
        from ai_bg import is_available
        if not is_available():
            print("[carousel] GEMINI_API_KEY нет — слайды без AI-фона (CSS-fallback)")
            return {}
    except Exception:
        return {}

    jobs: list[tuple[int, str]] = []  # (idx, hint)
    jobs.append((1, content["hero"].get("bg_hint", "minimalist premium desk, morning light")))
    for i, s in enumerate(content.get("slides", []), start=2):
        jobs.append((i, s.get("bg_hint", "abstract premium interior, soft light")))
    total = 1 + len(content.get("slides", [])) + 1
    jobs.append((total, content["cta"].get("bg_hint", "warm premium interior at dusk, city bokeh")))

    result: dict[int, str] = {}
    done = 0
    if progress:
        progress(f"🎨 Генерю AI-фоны слайдов (0/{len(jobs)})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        fut_map = {ex.submit(_gen_one_bg, hint, html_dir / f"bg-{idx:02d}.png"): idx for idx, hint in jobs}
        for fut in concurrent.futures.as_completed(fut_map):
            idx = fut_map[fut]
            path = fut.result()
            done += 1
            if path and path.exists():
                result[idx] = path.name
            if progress and done == max(1, len(jobs) // 2):
                progress(f"🎨 AI-фоны: {done}/{len(jobs)} готово, продолжаю...")
    print(f"[carousel] AI-фоны: {len(result)}/{len(jobs)} успешно")
    return result


def build_carousel(content: dict, out_dir: Path, ai_bg: bool = True, progress=None) -> list[Path]:
    """Строит HTML всех слайдов (+ AI-фоны), рендерит в PNG. Возвращает список PNG по порядку."""
    from render_card import render_html

    out_dir = Path(out_dir)
    html_dir = out_dir / "html"
    png_dir = out_dir / "png"
    html_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    slides_data = content.get("slides", [])
    total = 1 + len(slides_data) + 1  # hero + content + cta

    backgrounds: dict[int, str] = {}
    if ai_bg:
        backgrounds = generate_backgrounds(content, html_dir, progress)

    if progress:
        progress("🖼 Рендерю слайды в PNG...")

    htmls: list[tuple[str, str]] = []
    htmls.append(("slide-01", slide_hero(1, total, content["hero"], backgrounds.get(1))))
    for i, s in enumerate(slides_data, start=2):
        htmls.append((f"slide-{i:02d}", slide_content(i, total, s, backgrounds.get(i))))
    htmls.append((f"slide-{total:02d}", slide_cta(total, total, content["cta"], backgrounds.get(total))))

    pngs = []
    for name, html in htmls:
        hp = html_dir / f"{name}.html"
        hp.write_text(html, encoding="utf-8")
        pp = png_dir / f"{name}.png"
        render_html(hp, pp)
        pngs.append(pp)
    return pngs


def caption_md(content: dict) -> str:
    """Собирает подпись + хэштеги + первый коммент в один markdown-блок."""
    cap = content.get("caption", "")
    tags = " ".join(content.get("hashtags", []))
    fc = content.get("first_comment", "")
    return f"{cap}\n\n{tags}\n\n— Первый комментарий —\n{fc}"


def fetch_recent_facts(db, days: int = 7, limit: int = 40) -> str:
    """Берёт топ релевантных фактов из market-intel за N дней — для тем и контента карусели."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = db.conn.execute(
        """SELECT p.date, p.text,
                  MAX(CASE WHEN t.kind='importance' THEN CAST(t.value AS INTEGER) END) AS importance,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='developer' THEN t.value END) AS developers,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='zhk' THEN t.value END) AS zhk,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='bc' THEN t.value END) AS bc,
                  GROUP_CONCAT(DISTINCT CASE WHEN t.kind='topic' THEN t.value END) AS topics
           FROM posts p
           JOIN post_tags pt ON pt.post_id = p.id
           JOIN tags t ON t.id = pt.tag_id
           WHERE p.processed = 1 AND p.canonical_id IS NULL AND p.date >= ?
           GROUP BY p.id
           ORDER BY importance DESC, p.date DESC
           LIMIT ?""",
        (since, limit),
    )
    lines = []
    for r in cur.fetchall():
        d = dict(r)
        ent = " · ".join(filter(None, [
            (d.get("developers") or "").replace(",", ", "),
            (d.get("zhk") or "").replace(",", ", "),
            (d.get("bc") or "").replace(",", ", "),
        ])) or ""
        text = " ".join((d.get("text") or "").split())[:280]
        lines.append(f"[{d['date'][:10]}] ⭐{d.get('importance') or 3} {ent} — {text}")
    return "\n".join(lines) if lines else "Свежих фактов в базе нет."
