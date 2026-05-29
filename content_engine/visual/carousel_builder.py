"""Генератор каруселей: тема → Claude генерит структуру слайдов → HTML (фирстиль) → PNG.

Пайплайн:
  1. propose_topics(facts) — Claude предлагает 3 темы карусели из свежих фактов рынка
  2. generate_carousel_content(topic, facts) — Claude через tool_use возвращает структуру:
     { hook, slides: [{type, title, body, stat_label, stat_value}], cta, caption, hashtags }
  3. build_carousel(content, out_dir) — собирает HTML по фирстилю, рендерит в PNG через render_card
  4. Возвращает (png_paths, caption_md)

Фирстиль: палитра графит/слоновая кость/терракота, PT Serif + Inter, 1080×1350.
AI-фон опционален (если есть hero_bg.png — подкладывается на первый слайд).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
RENDER = HERE / "render_card.py"

# ── Фирстиль (inline CSS, Google Fonts CDN) ──────────────────────────────────
SLIDE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap');
:root{--bg:#14171C;--text:#F4F1EA;--accent:#B85C3C;--muted:#B5AFA3;--divider:rgba(244,241,234,0.18);}
*{margin:0;padding:0;box-sizing:border-box;-webkit-font-smoothing:antialiased;}
html,body{width:1080px;height:1350px;overflow:hidden;background:var(--bg);}
.slide{width:1080px;height:1350px;position:relative;color:var(--text);font-family:'Inter',sans-serif;
  padding:90px 80px;display:flex;flex-direction:column;overflow:hidden;}
.ai-bg{position:absolute;inset:0;background-size:cover;background-position:center;z-index:1;}
.grad{position:absolute;inset:0;z-index:2;background:linear-gradient(180deg,
  rgba(20,23,28,0.94) 0%,rgba(20,23,28,0.78) 20%,rgba(20,23,28,0.45) 45%,
  rgba(20,23,28,0.55) 70%,rgba(20,23,28,0.96) 100%);}
.content{position:relative;z-index:3;display:flex;flex-direction:column;height:100%;}
.label{display:inline-block;align-self:flex-start;padding:7px 16px;background:var(--accent);
  color:var(--text);font-weight:600;font-size:14px;letter-spacing:2.4px;text-transform:uppercase;border-radius:2px;}
.h1{font-family:'PT Serif',serif;font-weight:700;font-size:86px;line-height:0.98;letter-spacing:-2px;
  margin-top:28px;text-shadow:0 2px 32px rgba(0,0,0,0.6);}
.h2{font-family:'PT Serif',serif;font-weight:700;font-size:62px;line-height:1.05;letter-spacing:-1px;margin-top:10px;}
.sub{font-size:30px;line-height:1.4;opacity:0.95;margin-top:30px;max-width:840px;}
.body{font-size:34px;line-height:1.5;opacity:0.96;margin-top:34px;max-width:900px;}
.accent{color:var(--accent);}
.stat{margin-top:auto;display:flex;flex-direction:column;gap:6px;padding:34px 30px;
  background:rgba(20,23,28,0.66);backdrop-filter:blur(10px);border-left:4px solid var(--accent);width:fit-content;}
.stat-label{font-weight:500;font-size:18px;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted);}
.stat-value{font-family:'PT Serif',serif;font-weight:700;font-size:92px;line-height:1;color:var(--accent);}
.spacer{flex:1;}
.footer{position:relative;z-index:3;display:flex;justify-content:space-between;align-items:flex-end;
  margin-top:40px;padding-top:26px;border-top:1px solid var(--divider);font-size:22px;}
.brand{font-weight:600;}.brand .mut{color:var(--muted);font-weight:400;}
.handle{color:var(--muted);}
.pager{position:absolute;bottom:80px;right:70px;z-index:4;font-weight:600;font-size:15px;
  letter-spacing:1.5px;opacity:0.8;}
.cta-big{font-family:'PT Serif',serif;font-weight:700;font-size:70px;line-height:1.05;letter-spacing:-1px;}
.cta-sub{font-size:32px;line-height:1.45;opacity:0.95;margin-top:30px;max-width:880px;}
ul.points{margin-top:34px;list-style:none;}
ul.points li{font-size:32px;line-height:1.45;margin-bottom:26px;padding-left:44px;position:relative;}
ul.points li:before{content:'';position:absolute;left:0;top:16px;width:20px;height:3px;background:var(--accent);}
"""

BRAND_FOOTER = (
    '<div class="footer"><div class="brand">Иван Гладышев<span class="mut"> · недвижимость Москвы</span></div>'
    '<div class="handle">@IVAN_SUNSIDE</div></div>'
)


def _doc(inner: str, bg_url: str | None = None) -> str:
    bg = f'<div class="ai-bg" style="background-image:url(\'{bg_url}\');"></div><div class="grad"></div>' if bg_url else ""
    return (
        f'<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><style>{SLIDE_CSS}</style></head>'
        f'<body><div class="slide">{bg}<div class="content">{inner}</div></div></body></html>'
    )


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hl(s: str) -> str:
    """Подсветка *слова* → accent."""
    return re.sub(r"\*(.+?)\*", r'<span class="accent">\1</span>', esc(s))


def slide_hero(idx: int, total: int, label: str, title: str, sub: str,
               stat_label: str = "", stat_value: str = "", bg_url: str | None = None) -> str:
    stat = ""
    if stat_value:
        stat = f'<div class="stat"><div class="stat-label">{esc(stat_label)}</div><div class="stat-value">{esc(stat_value)}</div></div>'
    else:
        stat = '<div class="spacer"></div>'
    inner = (
        f'<div class="label">{esc(label)}</div>'
        f'<div class="h1">{hl(title)}</div>'
        f'<div class="sub">{hl(sub)}</div>'
        f'{stat}{BRAND_FOOTER}'
        f'<div class="pager">{idx:02d} / {total:02d} →</div>'
    )
    return _doc(inner, bg_url)


def slide_point(idx: int, total: int, title: str, body: str = "", points: list[str] | None = None,
                stat_label: str = "", stat_value: str = "") -> str:
    parts = [f'<div class="h2">{hl(title)}</div>']
    if body:
        parts.append(f'<div class="body">{hl(body)}</div>')
    if points:
        lis = "".join(f"<li>{hl(p)}</li>" for p in points)
        parts.append(f'<ul class="points">{lis}</ul>')
    if stat_value:
        parts.append(f'<div class="stat"><div class="stat-label">{esc(stat_label)}</div><div class="stat-value">{esc(stat_value)}</div></div>')
    else:
        parts.append('<div class="spacer"></div>')
    parts.append(BRAND_FOOTER)
    parts.append(f'<div class="pager">{idx:02d} / {total:02d} →</div>')
    return _doc("".join(parts))


def slide_cta(idx: int, total: int, title: str, sub: str) -> str:
    inner = (
        f'<div class="label">Решаю задачу капитала</div>'
        f'<div class="spacer"></div>'
        f'<div class="cta-big">{hl(title)}</div>'
        f'<div class="cta-sub">{hl(sub)}</div>'
        f'<div class="spacer"></div>{BRAND_FOOTER}'
        f'<div class="pager">{idx:02d} / {total:02d}</div>'
    )
    return _doc(inner)


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
    "description": "Создай структуру Instagram-карусели из 6-8 слайдов для премиум-эксперта по недвижимости.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hero": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Метка-категория, КАПСОМ, 2-4 слова"},
                    "title": {"type": "string", "description": "Хук-заголовок. Можно выделить *слово* звёздочками"},
                    "sub": {"type": "string", "description": "Подзаголовок-обещание ценности"},
                    "stat_label": {"type": "string"},
                    "stat_value": {"type": "string", "description": "Цифра-якорь, напр '238 млн ₽' или '' если нет"},
                },
                "required": ["label", "title", "sub"],
            },
            "slides": {
                "type": "array", "minItems": 4, "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "Текст слайда (можно пусто если есть points)"},
                        "points": {"type": "array", "items": {"type": "string"}, "description": "Буллеты (опционально)"},
                        "stat_label": {"type": "string"},
                        "stat_value": {"type": "string"},
                    },
                    "required": ["title"],
                },
            },
            "cta": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "CTA-заголовок"},
                    "sub": {"type": "string", "description": "Призыв написать в директ / задать вопрос"},
                },
                "required": ["title", "sub"],
            },
            "caption": {"type": "string", "description": "Подпись под публикацией для Instagram (до 1500 знаков, премиум tone of voice)"},
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

Правила текста слайдов:
- Слайд = 1 мысль. Короткие фразы. Цифры с источником.
- *Звёздочками* выделяй 1-2 ключевых слова на слайд (станут терракотовыми)
- stat_value — только когда есть яркая цифра-якорь
- Опирайся на переданные факты рынка, не выдумывай цифры

caption — премиум-подпись (НЕ дубль слайдов), 800-1500 знаков.
hashtags — ровно 5, премиум-формат (#НедвижимостьМосквы и т.п.).
first_comment — НЕ дубль подписи: провокация / +1 цифра / контраргумент."""


def generate_carousel_content(topic: str, facts: str, client: anthropic.Anthropic, model: str) -> dict | None:
    resp = client.messages.create(
        model=model, max_tokens=4000,
        system=CAROUSEL_SYSTEM,
        tools=[CAROUSEL_TOOL], tool_choice={"type": "tool", "name": "build_carousel"},
        messages=[{"role": "user", "content": (
            f"Тема карусели: «{topic}»\n\nСвежие факты рынка для опоры:\n{facts[:9000]}\n\n"
            f"Создай карусель из hero + 4-6 слайдов + cta по правилам."
        )}],
    )
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use":
            return b.input
    return None


def build_carousel(content: dict, out_dir: Path, hero_bg: Path | None = None) -> list[Path]:
    """Строит HTML всех слайдов, рендерит в PNG. Возвращает список PNG по порядку."""
    import sys
    sys.path.insert(0, str(HERE))
    from render_card import render_html

    out_dir = Path(out_dir)
    html_dir = out_dir / "html"
    png_dir = out_dir / "png"
    html_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    slides_data = content.get("slides", [])
    total = 1 + len(slides_data) + 1  # hero + slides + cta

    htmls: list[tuple[str, str]] = []

    # Hero
    h = content["hero"]
    bg_url = hero_bg.as_uri() if hero_bg and hero_bg.exists() else None
    htmls.append(("slide-01", slide_hero(1, total, h.get("label", ""), h["title"], h.get("sub", ""),
                                          h.get("stat_label", ""), h.get("stat_value", ""), bg_url)))

    # Middle slides
    for i, s in enumerate(slides_data, start=2):
        htmls.append((f"slide-{i:02d}", slide_point(
            i, total, s["title"], s.get("body", ""), s.get("points"),
            s.get("stat_label", ""), s.get("stat_value", ""))))

    # CTA
    cta = content["cta"]
    htmls.append((f"slide-{total:02d}", slide_cta(total, total, cta["title"], cta["sub"])))

    # Записываем HTML и рендерим
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
