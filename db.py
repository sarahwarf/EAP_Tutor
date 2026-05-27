import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "coursebot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                telegram_id     INTEGER PRIMARY KEY,
                username        TEXT,
                first_name      TEXT,
                language        TEXT DEFAULT 'en',
                reminder_freq   TEXT DEFAULT 'weekly',
                nudge_types     TEXT DEFAULT 'deadlines,readings',
                preferred_hour  INTEGER DEFAULT 9,
                joined_at       TEXT DEFAULT (datetime('now')),
                last_active     TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER NOT NULL,
                role            TEXT NOT NULL,   -- 'user' or 'assistant'
                content         TEXT NOT NULL,
                ts              TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (telegram_id) REFERENCES students(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS struggles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER NOT NULL,
                topic           TEXT NOT NULL,
                count           INTEGER DEFAULT 1,
                last_seen       TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (telegram_id) REFERENCES students(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS materials (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tag             TEXT NOT NULL,
                content         TEXT NOT NULL,
                file_type       TEXT,
                uploaded_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS instructor_notes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                note            TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now'))
            );
        """)


def upsert_student(telegram_id: int, username: str, first_name: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO students (telegram_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_active = datetime('now')
        """, (telegram_id, username, first_name))


def get_student(telegram_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def update_setting(telegram_id: int, key: str, value: str):
    allowed = {"language", "reminder_freq", "nudge_types", "preferred_hour"}
    if key not in allowed:
        raise ValueError(f"Unknown setting: {key}")
    with get_conn() as conn:
        conn.execute(
            f"UPDATE students SET {key} = ? WHERE telegram_id = ?", (value, telegram_id)
        )


def save_message(telegram_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (telegram_id, role, content) VALUES (?, ?, ?)",
            (telegram_id, role, content),
        )


def get_history(telegram_id: int, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE telegram_id = ?
               ORDER BY ts DESC LIMIT ?""",
            (telegram_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def log_struggle(telegram_id: int, topic: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO struggles (telegram_id, topic)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
        """, (telegram_id, topic))
        conn.execute("""
            UPDATE struggles SET count = count + 1, last_seen = datetime('now')
            WHERE telegram_id = ? AND topic = ?
        """, (telegram_id, topic))


def get_top_struggles(telegram_id: int, n: int = 3) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT topic, count FROM struggles
               WHERE telegram_id = ?
               ORDER BY count DESC LIMIT ?""",
            (telegram_id, n),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Materials ─────────────────────────────────────────────────────────────────

def save_material(tag: str, content: str, file_type: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO materials (tag, content, file_type) VALUES (?, ?, ?)",
            (tag, content, file_type),
        )


def get_all_materials() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, tag, content, file_type, uploaded_at FROM materials ORDER BY uploaded_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_materials_by_tag(tag: str) -> list[dict]:
    """Return materials whose tag contains any word from the search tag."""
    words = tag.lower().split()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tag, content FROM materials"
        ).fetchall()
    results = []
    for row in rows:
        row_tag = row["tag"].lower()
        if any(w in row_tag for w in words):
            results.append(dict(row))
    return results


def delete_material(material_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))


# ── Instructor notes ──────────────────────────────────────────────────────────

def save_instructor_note(note: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO instructor_notes (note) VALUES (?)", (note,))


def get_recent_instructor_notes(days: int = 7) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT note, created_at FROM instructor_notes
               WHERE created_at >= datetime('now', ?)
               ORDER BY created_at DESC""",
            (f"-{days} days",),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_instructor_notes():
    with get_conn() as conn:
        conn.execute("DELETE FROM instructor_notes")
