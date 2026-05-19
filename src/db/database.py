import sqlite3
from pathlib import Path

from ..config import settings

DB_PATH = Path(settings.data_dir) / "personal_agent.db"


def get_connection():
    """Return a new SQLite connection with WAL mode and FK enforcement.

    Always use this function instead of raw sqlite3.connect() — otherwise
    row_factory, WAL journal, and foreign keys will not be configured.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            trigger_at TEXT NOT NULL,
            recurrence TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            notified INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS shopping_lists (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shopping_items (
            id TEXT PRIMARY KEY,
            list_id TEXT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            quantity TEXT DEFAULT '',
            bought INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS todos (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS habits (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            target TEXT DEFAULT '',
            streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            last_checkin TEXT DEFAULT '',
            last_asked TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id TEXT PRIMARY KEY,
            habit_id TEXT NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'done',
            notes TEXT DEFAULT '',
            UNIQUE(habit_id, date)
        );

        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, notified, trigger_at);
        CREATE INDEX IF NOT EXISTS idx_shopping_items_list ON shopping_items(list_id);
        CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id, status, priority);
        CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(habit_id, date);
    """)
    conn.commit()
    conn.close()
