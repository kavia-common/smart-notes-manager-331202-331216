"""
Database module for Notes application.

Provides the SQLite database connection, table initialization, and a
dependency-injectable session/connection factory for use by FastAPI routes.

Contract:
  - Reads SQLITE_DB env var (or falls back to a local default) for the db path.
  - On startup, ensures tables (notes, tags, note_tags, notes_fts) exist.
  - Exposes get_db() as a FastAPI dependency that yields a sqlite3.Connection.
"""

import sqlite3
import logging
import os
from typing import Generator

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _resolve_db_path() -> str:
    """Return the SQLite database file path from env or a safe default."""
    path = os.getenv("SQLITE_DB", "notes.db")
    # The env var may be surrounded by quotes — strip them
    path = path.strip('"').strip("'")
    return path


DB_PATH: str = _resolve_db_path()

# ---------------------------------------------------------------------------
# Schema DDL
# Each statement is kept separate to avoid splitting multi-line BEGIN…END
# trigger bodies on semicolons.
# ---------------------------------------------------------------------------

_BASE_TABLES_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    title       TEXT     NOT NULL DEFAULT '',
    content     TEXT     NOT NULL DEFAULT '',
    is_markdown INTEGER  NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title,
    content,
    content='notes',
    content_rowid='id'
);
"""

# Triggers are defined individually so they are not split on inner semicolons
_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END
"""

_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END
"""

_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO notes_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END
"""


def _create_triggers(conn: sqlite3.Connection) -> None:
    """Create FTS sync triggers, ignoring 'already exists' errors."""
    for trigger_sql in (_TRIGGER_AI, _TRIGGER_AD, _TRIGGER_AU):
        try:
            conn.execute(trigger_sql.strip())
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc):
                logger.warning("Trigger creation warning: %s", exc)


def init_db() -> None:
    """
    Initialize the database schema.

    Creates all required tables, FTS virtual table, and sync triggers.
    Safe to call multiple times (idempotent).
    """
    logger.info("Initializing database at %s", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        # executescript handles multi-statement DDL correctly and auto-commits
        conn.executescript(_BASE_TABLES_SQL)
        # Re-enable FK after executescript (executescript implicitly commits)
        conn.execute("PRAGMA foreign_keys=ON")
        # Create triggers individually to avoid inner-semicolon splitting issues
        _create_triggers(conn)
        conn.commit()
        logger.info("Database schema initialized successfully")
    except Exception:
        conn.rollback()
        logger.exception("Failed to initialize database schema")
        raise
    finally:
        conn.close()


# PUBLIC_INTERFACE
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency that yields a SQLite connection.

    Usage::

        @app.get("/notes")
        def list_notes(db: sqlite3.Connection = Depends(get_db)):
            ...

    The connection has:
      - Row factory set to ``sqlite3.Row`` for dict-like row access.
      - Foreign keys enabled.
      - WAL journal mode for concurrent reads.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
