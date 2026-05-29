"""Синхронизация системных промптов агентов из .claude/agents/*.md в репо.

Зачем: на сервере НЕТ .claude/agents/ (это Claude Code субагенты в IDE).
Чтобы серверная «редакция» (agent_team.py) использовала ТЕ ЖЕ роли, что и
IDE-агенты, их системные промпты копируются (без YAML-frontmatter) в
content_engine/agents/<name>.md — этот каталог в репо market-intel и едет на сервер.

Запускать ЛОКАЛЬНО (где есть .claude/agents), результат коммитить:
    python content_engine/agents_sync.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../market-intel/content_engine
PROJECT_ROOT = HERE.parent.parent.parent        # .../Вайбкодинг
SRC = PROJECT_ROOT / ".claude" / "agents"
DST = HERE / "agents"

# Роли серверной команды, которые реально используем (не тащим всех 12).
WANTED = [
    "brand-strategist",
    "smm-strategist",
    "telegram-expert",
    "carousel-designer",
    "copywriter",
    "real-estate-expert",
]


def strip_frontmatter(text: str) -> str:
    """Убирает ведущий YAML-frontmatter (---...---), возвращает тело-промпт."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:].lstrip() if nl != -1 else ""
    return text.lstrip()


def main() -> int:
    if not SRC.exists():
        print(f"[sync] НЕТ {SRC} — запускать локально, где есть .claude/agents")
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    n = 0
    for name in WANTED:
        src = SRC / f"{name}.md"
        if not src.exists():
            print(f"[sync] ⚠ пропуск (нет файла): {name}")
            continue
        body = strip_frontmatter(src.read_text(encoding="utf-8"))
        (DST / f"{name}.md").write_text(body, encoding="utf-8")
        print(f"[sync] ✓ {name} ({len(body)} знаков)")
        n += 1
    print(f"[sync] Готово: {n} промптов → {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
