"""Первичная настройка: авторизация в Telegram, импорт addlist-папок, сохранение sources.yaml.

Запускать ОДИН раз после установки зависимостей и заполнения .env.

Что делает:
    1. Подключается к Telegram под аккаунтом из .env (попросит код подтверждения, потом 2FA пароль если включён)
    2. Если в .env заданы TELEGRAM_FOLDER_INVITES — присоединяет/обновляет shared-папки
    3. Читает список всех папок аккаунта (Dialog Filters)
    4. Для каждой папки из TELEGRAM_FOLDER_NAMES (или для всех addlist-папок, если список пуст)
       вытаскивает все каналы/чаты внутри и сохраняет в sources.yaml + в БД channels.
    5. Печатает итог в консоль.
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

import yaml
from telethon import TelegramClient
from telethon.tl import types
from telethon.tl.functions.chatlists import (
    CheckChatlistInviteRequest,
    JoinChatlistInviteRequest,
)
from telethon.tl.functions.messages import GetDialogFiltersRequest

import config
from db import DB


def extract_slug(invite_url: str) -> str:
    """Из https://t.me/addlist/xxxxx → xxxxx."""
    invite_url = invite_url.strip()
    if "/addlist/" in invite_url:
        return invite_url.rsplit("/addlist/", 1)[1].split("?")[0].split("/")[0]
    return invite_url


async def import_folder_invites(client: TelegramClient, invites: list[str]) -> None:
    if not invites:
        return
    print(f"[init] Импорт {len(invites)} addlist-папок...")
    for url in invites:
        slug = extract_slug(url)
        try:
            info = await client(CheckChatlistInviteRequest(slug=slug))
        except Exception as exc:
            print(f"  ✗ {url}: не удалось проверить ({exc})")
            continue

        already = isinstance(info, types.chatlists.ChatlistInviteAlready)
        peers = info.already_peers if already else info.peers
        new_peers = info.missing_peers if already else info.peers
        title = getattr(info, "title", None) or getattr(getattr(info, "filter", None), "title", None) or "(без названия)"
        print(f"  • {title}: уже добавлено {len(peers) if already else 0}, новых {len(new_peers)}")

        if new_peers:
            try:
                await client(JoinChatlistInviteRequest(slug=slug, peers=new_peers))
                print(f"    + присоединено: {len(new_peers)}")
            except Exception as exc:
                print(f"    ✗ не удалось присоединить: {exc}")


async def collect_folders(client: TelegramClient, wanted_names: list[str]) -> list[dict]:
    """Возвращает список папок: [{title, peers: [Peer, ...]}, ...].

    Если wanted_names пуст — берём все папки типа DialogFilterChatlist (то есть импортированные addlist).
    Иначе берём только папки с заданными названиями.
    """
    raw_filters = await client(GetDialogFiltersRequest())
    # Telethon отдаёт DialogFilters(filters=[...]); первый элемент часто DialogFilterDefault.
    filters = getattr(raw_filters, "filters", raw_filters)

    folders: list[dict] = []
    for f in filters:
        if isinstance(f, types.DialogFilterDefault):
            continue
        title_obj = getattr(f, "title", None)
        title = getattr(title_obj, "text", None) or (title_obj if isinstance(title_obj, str) else None) or "(без названия)"
        is_chatlist = isinstance(f, types.DialogFilterChatlist)

        if wanted_names:
            if title not in wanted_names:
                continue
        else:
            # По умолчанию берём только chatlist-папки (то, что прилетело из addlist-инвайтов)
            if not is_chatlist:
                continue

        peers = list(getattr(f, "include_peers", []) or [])
        folders.append({"title": title, "peers": peers, "is_chatlist": is_chatlist})

    return folders


async def main() -> int:
    api_id = int(config.env("TELEGRAM_API_ID", required=True))
    api_hash = config.env("TELEGRAM_API_HASH", required=True)
    phone = config.env("TELEGRAM_PHONE", required=True)
    invites = config.env_list("TELEGRAM_FOLDER_INVITES")
    wanted_names = config.env_list("TELEGRAM_FOLDER_NAMES")

    client = TelegramClient(str(config.SESSION_PATH), api_id, api_hash)
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"[init] Авторизован: {me.first_name} (@{me.username or '—'}, id={me.id})")

    await import_folder_invites(client, invites)
    folders = await collect_folders(client, wanted_names)

    if not folders:
        print("[init] ✗ Папок с каналами не найдено. Проверь TELEGRAM_FOLDER_NAMES в .env")
        await client.disconnect()
        return 1

    db = DB(config.DB_PATH)
    sources_out: list[dict] = []
    total_channels = 0
    active_tg_ids: list[int] = []  # авто-синк: что реально сейчас в папках

    for folder in folders:
        print(f"[init] Папка: {folder['title']} ({len(folder['peers'])} элементов)")
        channels: list[dict] = []
        for peer in folder["peers"]:
            try:
                entity = await client.get_entity(peer)
            except Exception as exc:
                print(f"    ✗ не удалось получить entity: {exc}")
                continue

            tg_id = entity.id
            username = getattr(entity, "username", None)
            title = getattr(entity, "title", None) or getattr(entity, "first_name", "(без названия)")

            is_chat = False
            if isinstance(entity, types.Channel):
                is_chat = bool(getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False))
            elif isinstance(entity, (types.Chat, types.ChatForbidden)):
                is_chat = True

            db.upsert_channel(tg_id=tg_id, username=username, title=title, is_chat=is_chat, folder=folder["title"])
            active_tg_ids.append(tg_id)
            channels.append({
                "tg_id": tg_id,
                "username": username,
                "title": title,
                "is_chat": is_chat,
            })
            total_channels += 1

        sources_out.append({
            "folder": folder["title"],
            "is_chatlist": folder["is_chatlist"],
            "channels": channels,
        })

    config.SOURCES_PATH.write_text(
        yaml.safe_dump(
            {"folders": sources_out},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    # Авто-синк: помечаем is_active=0 для каналов, выпавших из всех папок
    n_off, titles_off = db.deactivate_missing_channels(active_tg_ids)
    if n_off:
        print(f"[init] ⚙ Выпали из папок (помечены is_active=0, посты сохранены): {n_off}")
        for t in titles_off[:10]:
            print(f"    − {t}")
        if n_off > 10:
            print(f"    ... и ещё {n_off - 10}")
    else:
        print("[init] ⚙ Синк папок: всё на месте, удалённых нет")

    print(f"[init] ✓ Готово. Активных каналов: {total_channels}")
    print(f"[init] ✓ sources.yaml: {config.SOURCES_PATH}")
    print(f"[init] ✓ База: {config.DB_PATH}")

    db.close()
    await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
