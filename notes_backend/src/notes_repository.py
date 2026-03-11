"""
Notes repository — data-access layer for notes and tags.

All SQL interactions are centralised here. Routes call repository functions
and never construct SQL directly. This keeps the logic testable and prevents
ad-hoc query duplication.

Contract:
  Inputs:  sqlite3.Connection (from get_db dependency), validated Pydantic models
  Outputs: dict / list[dict] from sqlite3.Row objects
  Errors:  sqlite3.IntegrityError propagated; not-found cases return None
  Side effects: writes to the SQLite database file
"""

import sqlite3
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


def _ensure_tags(conn: sqlite3.Connection, tag_names: List[str]) -> List[int]:
    """
    Insert tags that do not yet exist and return their IDs in order.

    Invariant: tag names are normalised to lowercase stripped strings.
    """
    tag_ids: List[int] = []
    for raw_name in tag_names:
        name = raw_name.strip().lower()
        if not name:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
        )
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row:
            tag_ids.append(row["id"])
    return tag_ids


def _attach_tags(conn: sqlite3.Connection, note_id: int, tag_ids: List[int]) -> None:
    """Replace all tag associations for a note with the given tag IDs."""
    conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
    for tag_id in tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
            (note_id, tag_id),
        )


def _get_tag_names_for_note(conn: sqlite3.Connection, note_id: int) -> List[str]:
    """Return sorted list of tag names attached to a note."""
    rows = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN note_tags nt ON nt.tag_id = t.id
        WHERE nt.note_id = ?
        ORDER BY t.name
        """,
        (note_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _enrich_note(conn: sqlite3.Connection, note: Dict[str, Any]) -> Dict[str, Any]:
    """Add 'tags' list and normalise boolean field to a note dict."""
    note["tags"] = _get_tag_names_for_note(conn, note["id"])
    note["is_markdown"] = bool(note.get("is_markdown", 0))
    return note


# ---------------------------------------------------------------------------
# Public repository functions
# ---------------------------------------------------------------------------

# PUBLIC_INTERFACE
def create_note(
    conn: sqlite3.Connection,
    title: str,
    content: str,
    is_markdown: bool,
    tags: List[str],
) -> Dict[str, Any]:
    """
    Insert a new note and attach tags.

    Returns the created note dict (including 'tags' list).
    """
    logger.info("CreateNote flow — title=%r, tags=%r", title[:40], tags)
    cursor = conn.execute(
        """
        INSERT INTO notes (title, content, is_markdown)
        VALUES (?, ?, ?)
        """,
        (title, content, int(is_markdown)),
    )
    note_id = cursor.lastrowid
    tag_ids = _ensure_tags(conn, tags)
    _attach_tags(conn, note_id, tag_ids)
    note = _row_to_dict(
        conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    )
    result = _enrich_note(conn, note)
    logger.info("CreateNote success — id=%d", note_id)
    return result


# PUBLIC_INTERFACE
def get_note(conn: sqlite3.Connection, note_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch a single note by primary key.

    Returns the note dict or None if not found.
    """
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        return None
    return _enrich_note(conn, _row_to_dict(row))


# PUBLIC_INTERFACE
def list_notes(
    conn: sqlite3.Connection,
    skip: int = 0,
    limit: int = 20,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return a paginated list of notes, optionally filtered by tag.

    Returns dict with 'total' (int) and 'items' (list of note dicts).
    """
    logger.debug("ListNotes — skip=%d, limit=%d, tag=%r", skip, limit, tag)

    if tag:
        tag_norm = tag.strip().lower()
        count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT n.id) FROM notes n
            JOIN note_tags nt ON nt.note_id = n.id
            JOIN tags t ON t.id = nt.tag_id
            WHERE t.name = ?
            """,
            (tag_norm,),
        ).fetchone()
        total = count_row[0] if count_row else 0

        rows = conn.execute(
            """
            SELECT DISTINCT n.* FROM notes n
            JOIN note_tags nt ON nt.note_id = n.id
            JOIN tags t ON t.id = nt.tag_id
            WHERE t.name = ?
            ORDER BY n.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (tag_norm, limit, skip),
        ).fetchall()
    else:
        count_row = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
        total = count_row[0] if count_row else 0

        rows = conn.execute(
            """
            SELECT * FROM notes
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
        ).fetchall()

    items = [_enrich_note(conn, _row_to_dict(r)) for r in rows]
    return {"total": total, "items": items}


# PUBLIC_INTERFACE
def update_note(
    conn: sqlite3.Connection,
    note_id: int,
    title: Optional[str],
    content: Optional[str],
    is_markdown: Optional[bool],
    tags: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    """
    Partially update a note.  Only provided (non-None) fields are changed.

    Returns the updated note dict or None if not found.
    """
    logger.info("UpdateNote flow — id=%d", note_id)
    existing = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if existing is None:
        return None

    # Build dynamic SET clause from non-None fields
    updates: List[str] = []
    params: List[Any] = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if is_markdown is not None:
        updates.append("is_markdown = ?")
        params.append(int(is_markdown))

    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(note_id)
        conn.execute(
            f"UPDATE notes SET {', '.join(updates)} WHERE id = ?",
            params,
        )

    if tags is not None:
        tag_ids = _ensure_tags(conn, tags)
        _attach_tags(conn, note_id, tag_ids)

    note = _row_to_dict(
        conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    )
    result = _enrich_note(conn, note)
    logger.info("UpdateNote success — id=%d", note_id)
    return result


# PUBLIC_INTERFACE
def delete_note(conn: sqlite3.Connection, note_id: int) -> bool:
    """
    Delete a note by primary key.

    Returns True if a row was deleted, False if not found.
    """
    logger.info("DeleteNote flow — id=%d", note_id)
    cursor = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("DeleteNote success — id=%d", note_id)
    else:
        logger.warning("DeleteNote — note id=%d not found", note_id)
    return deleted


# PUBLIC_INTERFACE
def search_notes(
    conn: sqlite3.Connection,
    query: str,
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Full-text search notes using SQLite FTS5.

    Falls back to a LIKE query if FTS is unavailable.
    Optionally filters by tag.

    Returns dict with 'total' (int) and 'items' (list of note dicts).
    """
    logger.info("SearchNotes flow — q=%r, tag=%r, skip=%d, limit=%d", query, tag, skip, limit)

    # Sanitise query for FTS (escape special characters)
    fts_query = query.replace('"', '""')

    try:
        if tag:
            tag_norm = tag.strip().lower()
            count_row = conn.execute(
                """
                SELECT COUNT(DISTINCT n.id) FROM notes n
                JOIN notes_fts fts ON fts.rowid = n.id
                JOIN note_tags nt ON nt.note_id = n.id
                JOIN tags t ON t.id = nt.tag_id
                WHERE notes_fts MATCH ? AND t.name = ?
                """,
                (fts_query, tag_norm),
            ).fetchone()
            total = count_row[0] if count_row else 0

            rows = conn.execute(
                """
                SELECT DISTINCT n.* FROM notes n
                JOIN notes_fts fts ON fts.rowid = n.id
                JOIN note_tags nt ON nt.note_id = n.id
                JOIN tags t ON t.id = nt.tag_id
                WHERE notes_fts MATCH ? AND t.name = ?
                ORDER BY n.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (fts_query, tag_norm, limit, skip),
            ).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH ?",
                (fts_query,),
            ).fetchone()
            total = count_row[0] if count_row else 0

            rows = conn.execute(
                """
                SELECT n.* FROM notes n
                JOIN notes_fts fts ON fts.rowid = n.id
                WHERE notes_fts MATCH ?
                ORDER BY n.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (fts_query, limit, skip),
            ).fetchall()

    except sqlite3.OperationalError:
        # FTS not available – fall back to LIKE
        logger.warning("FTS search failed, using LIKE fallback for query=%r", query)
        like_q = f"%{query}%"
        if tag:
            tag_norm = tag.strip().lower()
            count_row = conn.execute(
                """
                SELECT COUNT(DISTINCT n.id) FROM notes n
                JOIN note_tags nt ON nt.note_id = n.id
                JOIN tags t ON t.id = nt.tag_id
                WHERE (n.title LIKE ? OR n.content LIKE ?) AND t.name = ?
                """,
                (like_q, like_q, tag_norm),
            ).fetchone()
            total = count_row[0] if count_row else 0
            rows = conn.execute(
                """
                SELECT DISTINCT n.* FROM notes n
                JOIN note_tags nt ON nt.note_id = n.id
                JOIN tags t ON t.id = nt.tag_id
                WHERE (n.title LIKE ? OR n.content LIKE ?) AND t.name = ?
                ORDER BY n.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (like_q, like_q, tag_norm, limit, skip),
            ).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM notes WHERE title LIKE ? OR content LIKE ?",
                (like_q, like_q),
            ).fetchone()
            total = count_row[0] if count_row else 0
            rows = conn.execute(
                """
                SELECT * FROM notes
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (like_q, like_q, limit, skip),
            ).fetchall()

    items = [_enrich_note(conn, _row_to_dict(r)) for r in rows]
    logger.info("SearchNotes success — total=%d, returned=%d", total, len(items))
    return {"total": total, "items": items}


# PUBLIC_INTERFACE
def list_tags(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Return all tags ordered alphabetically.

    Returns list of dicts with 'id' and 'name'.
    """
    rows = conn.execute("SELECT id, name FROM tags ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


# PUBLIC_INTERFACE
def delete_tag(conn: sqlite3.Connection, tag_id: int) -> bool:
    """
    Delete a tag by primary key.

    Cascades to note_tags via FK constraint.
    Returns True if deleted, False if not found.
    """
    cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    return cursor.rowcount > 0
