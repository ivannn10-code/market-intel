"""SQLite-хранилище постов с полнотекстовым поиском (FTS5).

Схема:
    channels — справочник каналов
    posts    — все спарсенные посты
    posts_fts — виртуальная FTS5-таблица для быстрого поиска по тексту
    tags     — теги, присвоенные процессором (застройщик / ЖК / тема)
    post_tags — связь many-to-many

Использование из агентов:
    sqlite3 intel.db "SELECT date, channel, text FROM posts JOIN channels ON posts.channel_id=channels.id WHERE posts MATCH 'эскроу' ORDER BY date DESC LIMIT 20"
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY,
    tg_id       INTEGER UNIQUE NOT NULL,
    username    TEXT,
    title       TEXT NOT NULL,
    is_chat     INTEGER NOT NULL DEFAULT 0,
    folder      TEXT,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY,
    channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    tg_msg_id   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    text        TEXT NOT NULL,
    text_hash   TEXT NOT NULL,
    views       INTEGER,
    forwards    INTEGER,
    reply_to    INTEGER,
    has_media   INTEGER NOT NULL DEFAULT 0,
    url         TEXT,
    processed   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(channel_id, tg_msg_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date);
CREATE INDEX IF NOT EXISTS idx_posts_processed ON posts(processed);
CREATE INDEX IF NOT EXISTS idx_posts_hash ON posts(text_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
    text,
    content='posts',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
    INSERT INTO posts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO posts_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER PRIMARY KEY,
    kind    TEXT NOT NULL,
    value   TEXT NOT NULL,
    UNIQUE(kind, value)
);

CREATE TABLE IF NOT EXISTS post_tags (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_post_tags_tag ON post_tags(tag_id);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    posts_new   INTEGER DEFAULT 0,
    posts_seen  INTEGER DEFAULT 0,
    errors      TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    post_id     INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    sent_at     TEXT NOT NULL,
    kind        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_state (
    chat_id     TEXT PRIMARY KEY,
    state       TEXT NOT NULL DEFAULT 'idle',
    payload     TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_offset (
    id          INTEGER PRIMARY KEY CHECK (id=1),
    update_id   INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO bot_offset (id, update_id) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS bot_chat_history (
    id          INTEGER PRIMARY KEY,
    chat_id     TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_history_chat ON bot_chat_history(chat_id, created_at);

CREATE TABLE IF NOT EXISTS bot_last_post (
    chat_id     TEXT PRIMARY KEY,
    post_path   TEXT NOT NULL,
    rubric      TEXT,
    topic       TEXT,
    created_at  TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Идемпотентные миграции — выполняются при каждом старте, безопасны."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(posts)")}
        if "canonical_id" not in cols:
            self.conn.execute("ALTER TABLE posts ADD COLUMN canonical_id INTEGER")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_canonical ON posts(canonical_id)")
        if "fingerprint" not in cols:
            self.conn.execute("ALTER TABLE posts ADD COLUMN fingerprint TEXT")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_fingerprint ON posts(fingerprint)")

    def close(self):
        self.conn.close()

    @contextmanager
    def tx(self):
        self.conn.execute("BEGIN")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def upsert_channel(self, tg_id: int, username: str | None, title: str, is_chat: bool, folder: str | None) -> int:
        cur = self.conn.execute(
            """INSERT INTO channels (tg_id, username, title, is_chat, folder, added_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(tg_id) DO UPDATE SET
                 username=excluded.username,
                 title=excluded.title,
                 folder=excluded.folder
               RETURNING id""",
            (tg_id, username, title, 1 if is_chat else 0, folder, datetime.utcnow().isoformat()),
        )
        return cur.fetchone()[0]

    def post_exists(self, channel_id: int, tg_msg_id: int) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM posts WHERE channel_id=? AND tg_msg_id=? LIMIT 1",
            (channel_id, tg_msg_id),
        )
        return cur.fetchone() is not None

    def insert_post(
        self,
        channel_id: int,
        tg_msg_id: int,
        date: str,
        text: str,
        text_hash: str,
        views: int | None,
        forwards: int | None,
        reply_to: int | None,
        has_media: bool,
        url: str | None,
    ) -> int | None:
        try:
            cur = self.conn.execute(
                """INSERT INTO posts (channel_id, tg_msg_id, date, text, text_hash, views, forwards, reply_to, has_media, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (channel_id, tg_msg_id, date, text, text_hash, views, forwards, reply_to, 1 if has_media else 0, url),
            )
            return cur.fetchone()[0]
        except sqlite3.IntegrityError:
            return None

    def unprocessed_posts(self, limit: int = 200) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """SELECT p.id, p.date, p.text, p.url, c.title AS channel_title, c.username AS channel_username
               FROM posts p JOIN channels c ON c.id = p.channel_id
               WHERE p.processed = 0
               ORDER BY p.date ASC
               LIMIT ?""",
            (limit,),
        )
        return cur.fetchall()

    def unprocessed_posts_deduped(self, limit: int = 200) -> list[dict]:
        """То же что unprocessed_posts, но дублирующие посты (один и тот же текст в N каналах)
        возвращает одной записью, с дополнительным полем `also_in` = ["@ch1", "@ch2", ...]
        и `dup_ids` = [post_id, ...] (все ID этой группы — чтобы все пометить processed)."""
        cur = self.conn.execute(
            """SELECT p.id, p.date, p.text, p.text_hash, p.url, p.channel_id,
                      c.title AS channel_title, c.username AS channel_username
               FROM posts p JOIN channels c ON c.id = p.channel_id
               WHERE p.processed = 0
               ORDER BY p.date ASC"""
        )
        rows = cur.fetchall()

        # Группируем по text_hash, оставляя самый ранний
        groups: dict[str, dict] = {}
        for r in rows:
            h = r["text_hash"]
            if h not in groups:
                groups[h] = {
                    "id": r["id"],
                    "date": r["date"],
                    "text": r["text"],
                    "url": r["url"],
                    "channel_title": r["channel_title"],
                    "channel_username": r["channel_username"],
                    "also_in": [],
                    "dup_ids": [r["id"]],
                }
            else:
                # Это дубль — добавим канал в also_in
                src = f"@{r['channel_username']}" if r["channel_username"] else r["channel_title"]
                if src not in groups[h]["also_in"]:
                    groups[h]["also_in"].append(src)
                groups[h]["dup_ids"].append(r["id"])

        result = list(groups.values())
        result.sort(key=lambda x: x["date"])
        return result[:limit]

    def mark_processed(self, post_ids: Iterable[int]):
        self.conn.executemany("UPDATE posts SET processed=1 WHERE id=?", [(i,) for i in post_ids])

    def add_tag(self, kind: str, value: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO tags (kind, value) VALUES (?, ?)
               ON CONFLICT(kind, value) DO UPDATE SET value=excluded.value
               RETURNING id""",
            (kind, value),
        )
        return cur.fetchone()[0]

    def link_tag(self, post_id: int, tag_id: int):
        self.conn.execute(
            "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
            (post_id, tag_id),
        )

    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at) VALUES (?) RETURNING id",
            (datetime.utcnow().isoformat(),),
        )
        return cur.fetchone()[0]

    def finish_run(self, run_id: int, posts_new: int, posts_seen: int, errors: str | None = None):
        self.conn.execute(
            """UPDATE runs SET finished_at=?, posts_new=?, posts_seen=?, errors=?
               WHERE id=?""",
            (datetime.utcnow().isoformat(), posts_new, posts_seen, errors, run_id),
        )

    def find_canonical_by_fingerprint(self, fingerprint: str, exclude_post_id: int) -> int | None:
        """Возвращает id canonical-поста с тем же fingerprint, если есть.
        Canonical — это пост, у которого canonical_id IS NULL (т.е. он сам — родитель).
        Возвращает самый ранний такой пост (по дате)."""
        cur = self.conn.execute(
            """SELECT id FROM posts
               WHERE fingerprint = ? AND id != ? AND canonical_id IS NULL
               ORDER BY date ASC LIMIT 1""",
            (fingerprint, exclude_post_id),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_fingerprint(self, post_id: int, fingerprint: str):
        self.conn.execute("UPDATE posts SET fingerprint=? WHERE id=?", (fingerprint, post_id))

    def mark_as_dup(self, post_id: int, canonical_id: int):
        self.conn.execute("UPDATE posts SET canonical_id=? WHERE id=?", (canonical_id, post_id))

    def get_duplicate_channels(self, canonical_id: int) -> list[str]:
        """Возвращает список @username каналов, где этот факт повторился (для пометки 'также в:')."""
        cur = self.conn.execute(
            """SELECT DISTINCT c.username, c.title FROM posts p
               JOIN channels c ON c.id = p.channel_id
               WHERE p.canonical_id = ?""",
            (canonical_id,),
        )
        result = []
        for r in cur.fetchall():
            result.append(f"@{r['username']}" if r["username"] else r["title"])
        return result

    def was_notified(self, post_id: int) -> bool:
        cur = self.conn.execute("SELECT 1 FROM notifications WHERE post_id=?", (post_id,))
        return cur.fetchone() is not None

    # === Chat history ===

    def add_chat_message(self, chat_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO bot_chat_history (chat_id, role, content, created_at)
               VALUES (?, ?, ?, ?) RETURNING id""",
            (chat_id, role, content, datetime.utcnow().isoformat()),
        )
        return cur.fetchone()[0]

    def get_chat_history(self, chat_id: str, limit: int = 20) -> list[dict]:
        """Возвращает последние N сообщений диалога (в хронологическом порядке)."""
        cur = self.conn.execute(
            """SELECT role, content FROM bot_chat_history
               WHERE chat_id = ? ORDER BY id DESC LIMIT ?""",
            (chat_id, limit),
        )
        rows = list(cur.fetchall())
        rows.reverse()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def clear_chat_history(self, chat_id: str):
        self.conn.execute("DELETE FROM bot_chat_history WHERE chat_id = ?", (chat_id,))

    # === Last post tracking (для перегенерации) ===

    def save_last_post(self, chat_id: str, post_path: str, rubric: str | None, topic: str | None):
        self.conn.execute(
            """INSERT INTO bot_last_post (chat_id, post_path, rubric, topic, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 post_path=excluded.post_path,
                 rubric=excluded.rubric,
                 topic=excluded.topic,
                 created_at=excluded.created_at""",
            (chat_id, post_path, rubric, topic, datetime.utcnow().isoformat()),
        )

    def get_last_post(self, chat_id: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT post_path, rubric, topic, created_at FROM bot_last_post WHERE chat_id=?",
            (chat_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    # === Bot states ===

    def get_bot_state(self, chat_id: str) -> tuple[str, str | None]:
        cur = self.conn.execute("SELECT state, payload FROM bot_state WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()
        return (row["state"], row["payload"]) if row else ("idle", None)

    def set_bot_state(self, chat_id: str, state: str, payload: str | None = None):
        self.conn.execute(
            """INSERT INTO bot_state (chat_id, state, payload, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 state=excluded.state, payload=excluded.payload, updated_at=excluded.updated_at""",
            (chat_id, state, payload, datetime.utcnow().isoformat()),
        )

    def get_bot_offset(self) -> int:
        cur = self.conn.execute("SELECT update_id FROM bot_offset WHERE id=1")
        row = cur.fetchone()
        return row["update_id"] if row else 0

    def set_bot_offset(self, update_id: int):
        self.conn.execute("UPDATE bot_offset SET update_id=? WHERE id=1", (update_id,))

    def mark_notified(self, post_id: int, kind: str = "alert"):
        self.conn.execute(
            "INSERT OR IGNORE INTO notifications (post_id, sent_at, kind) VALUES (?, ?, ?)",
            (post_id, datetime.utcnow().isoformat(), kind),
        )
