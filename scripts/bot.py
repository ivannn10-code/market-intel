"""Минимальный клиент Telegram Bot API.

Без внешних зависимостей кроме requests (есть в venv через httpx Anthropic SDK).
Если requests нет, используем urllib.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import config


def _request(method: str, payload: dict) -> dict:
    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(method: str, params: dict | None = None) -> dict:
    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_me() -> dict:
    return _get("getMe")


def set_my_commands(commands: list[dict]) -> dict:
    """Регистрирует список команд для нативной кнопки «Меню» (слева от поля ввода).
    commands: [{"command": "menu", "description": "Открыть меню"}, ...]"""
    try:
        return _request("setMyCommands", {"commands": commands})
    except Exception:
        return {}


def set_chat_menu_button_commands() -> dict:
    """Делает нативную кнопку Menu списком команд (дефолт Telegram)."""
    try:
        return _request("setChatMenuButton", {"menu_button": {"type": "commands"}})
    except Exception:
        return {}


def get_updates(offset: int | None = None, timeout: int = 25, allowed_updates: list[str] | None = None) -> list[dict]:
    """Long polling getUpdates."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    if allowed_updates:
        params["allowed_updates"] = json.dumps(allowed_updates)
    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/getUpdates?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout + 5) as resp:
            r = json.loads(resp.read().decode("utf-8"))
            return r.get("result", []) if r.get("ok") else []
    except (urllib.error.URLError, TimeoutError):
        return []


def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False):
    """Ответ на нажатие inline-кнопки — снимает 'часики' с кнопки."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    try:
        _request("answerCallbackQuery", payload)
    except Exception:
        pass


def send_chat_action(chat_id: str | int, action: str = "typing") -> None:
    """Показать «печатает...» в чате. Полезно перед долгими LLM-запросами.

    action: typing, upload_photo, record_video, upload_video, record_voice,
            upload_voice, upload_document, find_location."""
    try:
        _request("sendChatAction", {"chat_id": chat_id, "action": action})
    except Exception:
        pass  # не критично, не блокируем основной поток


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
    buttons: list[list[dict]] | None = None,
    reply_keyboard: list[list[str]] | None = None,
    remove_keyboard: bool = False,
) -> dict:
    """Отправить сообщение. Если text длиннее 4096, режется на части.

    buttons         — двумерный массив inline-кнопок:
                      [[{"text": "...", "url": "..."}], [...]]
                      Привязываются только к ПОСЛЕДНЕЙ части.
    reply_keyboard  — постоянная клавиатура внизу экрана:
                      [["📊 Сводка"], ["🔍 Аналитика", "🌡 Sentiment"]]
                      Тоже только к последней части.
    remove_keyboard — убрать нижнюю клавиатуру (после завершения диалога).
    """
    chunks = _split_text(text, 4000)
    last = None
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if i == len(chunks) - 1:
            if buttons:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            elif reply_keyboard:
                payload["reply_markup"] = {
                    "keyboard": [[{"text": t} for t in row] for row in reply_keyboard],
                    "resize_keyboard": True,
                    "is_persistent": True,
                }
            elif remove_keyboard:
                payload["reply_markup"] = {"remove_keyboard": True}
        try:
            last = _request("sendMessage", payload)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
            raise RuntimeError(f"Telegram API error {exc.code}: {body}") from exc
        time.sleep(0.3)
    return last or {}


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks


HTML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def html_escape(text: str) -> str:
    """Escape для HTML parse_mode. Telegram HTML минимальный, нужно только &, <, >."""
    for k, v in HTML_ESCAPE.items():
        text = text.replace(k, v)
    return text


def send_pre(chat_id: str | int, body: str, *, buttons: list[list[dict]] | None = None) -> dict:
    """Шлёт body в <pre>-блоке для one-tap copy. Большое тело режется по строкам
    на несколько САМОСТОЯТЕЛЬНЫХ <pre>-сообщений (никогда не разрывает тег пополам).
    buttons прикрепляются только к последнему сообщению (так же, как в send_message)."""
    body = (body or "").strip()
    MAX = 3800  # запас от лимита 4096; включает накладные расходы <pre></pre>
    # Режем body на куски по строкам, каждый — целый <pre>...</pre>.
    if len(body) <= MAX:
        chunks = [body]
    else:
        chunks = []
        cur = ""
        for line in body.split("\n"):
            if len(cur) + len(line) + 1 > MAX:
                if cur:
                    chunks.append(cur)
                cur = line
            else:
                cur = cur + "\n" + line if cur else line
        if cur:
            chunks.append(cur)
    last = None
    for i, ch in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        payload_text = f"<pre>{html_escape(ch)}</pre>"
        last = send_message(
            chat_id, payload_text,
            buttons=(buttons if (is_last and buttons) else None),
        )
    return last or {}


def send_document(chat_id: str | int, document_path: Path, caption: str = "") -> dict:
    """Отправить файл (PDF, XLSX, и т.п.) через sendDocument."""
    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    boundary = uuid.uuid4().hex
    body = _build_multipart(
        boundary,
        fields={
            "chat_id": str(chat_id),
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"document": document_path},
    )

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"Telegram API error {exc.code}: {body_text}") from exc


def send_photo(chat_id: str | int, photo_path: Path, caption: str = "") -> dict:
    """Отправить одну фотографию через multipart/form-data."""
    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    boundary = uuid.uuid4().hex
    body = _build_multipart(
        boundary,
        fields={
            "chat_id": str(chat_id),
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"photo": photo_path},
    )

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"Telegram API error {exc.code}: {body_text}") from exc


def send_media_group(chat_id: str | int, photo_paths: list[Path], caption: str = "") -> dict:
    """Отправить альбом из 2-10 фото (Telegram media group = Instagram-style карусель в чате).

    caption прикрепляется к первой фотографии (макс 1024 знака).
    Если caption пустой — альбом без подписи.
    """
    if not (2 <= len(photo_paths) <= 10):
        raise ValueError(f"Media group requires 2-10 photos, got {len(photo_paths)}")

    token = config.env("TELEGRAM_BOT_TOKEN", required=True)
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"

    media = []
    files = {}
    for i, p in enumerate(photo_paths):
        file_key = f"photo_{i}"
        item = {
            "type": "photo",
            "media": f"attach://{file_key}",
        }
        if i == 0 and caption:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)
        files[file_key] = p

    boundary = uuid.uuid4().hex
    body = _build_multipart(
        boundary,
        fields={
            "chat_id": str(chat_id),
            "media": json.dumps(media, ensure_ascii=False),
        },
        files=files,
    )

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"Telegram API error {exc.code}: {body_text}") from exc


def _build_multipart(boundary: str, fields: dict[str, str], files: dict[str, Path]) -> bytes:
    """Сборка multipart/form-data тела вручную (без requests)."""
    lines = []
    eol = b"\r\n"

    for key, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"")
        lines.append(str(value).encode("utf-8"))

    for key, path in files.items():
        path = Path(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{path.name}"'.encode()
        )
        lines.append(f"Content-Type: {mime}".encode())
        lines.append(b"")
        lines.append(path.read_bytes())

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    return eol.join(lines)
