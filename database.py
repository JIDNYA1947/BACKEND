"""
SQLite database layer.

Provides:
- get_connection(): a context-managed sqlite3 connection with Row factory
- init_db(): creates all required tables if they do not already exist

Tables:
- loans
- survey_requests
- survey_responses
- mentor_alerts
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection():
    """Context manager yielding a sqlite3 connection; commits or rolls back safely."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS loans (
                loan_id       TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                phone_number  TEXT NOT NULL,
                business_name TEXT NOT NULL,
                loan_amount   REAL NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS survey_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id     TEXT NOT NULL,
                sent_at     TEXT NOT NULL,
                channel     TEXT NOT NULL DEFAULT 'whatsapp',
                status      TEXT NOT NULL,
                FOREIGN KEY (loan_id) REFERENCES loans (loan_id)
            );

            CREATE TABLE IF NOT EXISTS survey_responses (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id            TEXT NOT NULL,
                sales_status       TEXT NOT NULL,
                emi_status         TEXT NOT NULL,
                issue_status       TEXT NOT NULL,
                concerning_count   INTEGER NOT NULL,
                raw_message        TEXT,
                created_at         TEXT NOT NULL,
                FOREIGN KEY (loan_id) REFERENCES loans (loan_id)
            );

            CREATE TABLE IF NOT EXISTS mentor_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id     TEXT NOT NULL,
                reason      TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                resolved    INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (loan_id) REFERENCES loans (loan_id)
            );
            """
        )
