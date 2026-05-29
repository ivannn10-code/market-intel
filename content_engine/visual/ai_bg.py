"""Self-contained генератор AI-фонов для слайдов карусели через Google Gemini.

Намеренно НЕ зависит от .business/visual-pipeline/ (тот код вне репозитория
market-intel и на сервер не деплоится). Здесь — минимальный urllib-клиент,
который едет вместе с карусельным пайплайном.

Использование:
    from ai_bg import generate_bg, BRAND_TAIL, build_bg_prompt
    generate_bg(build_bg_prompt("стол с документами, ключи, утренний свет"), out_png)

Требует GEMINI_API_KEY в окружении (или в scripts/.env, который подхватывает бот).
Модель: GEMINI_IMAGE_MODEL (по умолчанию gemini-2.5-flash-image — Nano Banana).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# Бренд-tail из CLAUDE.md — приклеивается к каждому промпту, чтобы визуал
# не вылезал из tone-of-voice. Только обобщённые метафоры, без реальных ЖК/БЦ/лиц.
BRAND_TAIL = (
    "cinematic editorial photography, modern premium aesthetic, "
    "palette of deep teal (#0F3D4A), steel blue (#4A6A7B), warm light greige (#E7E2D8) "
    "and a singular vivid orange accent (#FF5A2A), shot on medium format with soft "
    "directional light, controlled saturation, no Instagram-filter look, "
    "architectural/interior magazine quality, vertical 4:5 composition, generous "
    "negative space, deep teal shadows for text overlay, no text, no logos, "
    "no watermarks, no human faces, no real recognizable buildings — only generalized metaphors."
)


def build_bg_prompt(hint: str) -> str:
    """Оборачивает короткую визуальную подсказку в безопасный премиум-промпт."""
    hint = (hint or "abstract premium real-estate scene").strip().rstrip(".")
    return f"{hint}. {BRAND_TAIL}"


def _env_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    # подхватим из scripts/.env, если модуль зовут вне бота
    here = Path(__file__).resolve()
    for up in here.parents:
        env = up / "scripts" / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY=") and "=" in line:
                    return line.split("=", 1)[1].strip()
    return None


def generate_bg(
    prompt: str,
    output: Path,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
    max_attempts: int = 3,
) -> Path:
    """Генерит одно изображение и пишет в output. Бросает RuntimeError при неудаче."""
    key = _env_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY не задан (ни в env, ни в scripts/.env)")

    url = f"{API_BASE}/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    body = json.dumps(payload).encode("utf-8")

    response: dict | None = None
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                response = json.loads(resp.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            if exc.code >= 500 or (exc.code == 429 and "limit: 0" not in err_body):
                last_err = RuntimeError(f"Gemini {exc.code}: {err_body[:200]}")
                if attempt < max_attempts:
                    time.sleep(2 ** attempt)
                    continue
            raise RuntimeError(f"Gemini API error {exc.code}: {err_body[:300]}") from exc
        except urllib.error.URLError as exc:
            last_err = exc
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Gemini недоступен после {max_attempts} попыток: {exc}") from exc

    if response is None:
        raise RuntimeError(f"Gemini не ответил: {last_err}")

    candidates = response.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Пустой ответ Gemini: {json.dumps(response)[:300]}")

    image_data: bytes | None = None
    text_notes: list[str] = []
    for part in candidates[0].get("content", {}).get("parts", []):
        inline = part.get("inline_data") or part.get("inlineData")
        if inline:
            image_data = base64.b64decode(inline["data"])
        elif "text" in part:
            text_notes.append(part["text"])

    if image_data is None:
        raise RuntimeError(
            "Gemini не вернул изображение (возможно фильтр безопасности). "
            f"Текст: {' | '.join(text_notes)[:300]}"
        )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_data)
    return output


def is_available() -> bool:
    return bool(_env_key())


if __name__ == "__main__":
    # smoke-test: python ai_bg.py "стол, ключи, утренний свет" out.png
    p = sys.argv[1] if len(sys.argv) > 1 else "minimalist desk with keys and documents, morning light"
    o = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("ai_bg_test.png")
    print("model:", DEFAULT_MODEL, "key:", "set" if is_available() else "MISSING")
    started = time.time()
    generate_bg(build_bg_prompt(p), o)
    print(f"OK {o} ({o.stat().st_size//1024} KB) in {time.time()-started:.1f}s")
