"""
API routes for the Notes application.

Groups:
  /notes  — CRUD for notes
  /tags   — tag management
  /search — full-text search

All routes are documented for Swagger UI and openapi.json.
"""

import sqlite3
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.database import get_db
from src.schemas import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteListResponse,
    TagResponse,
)
import src.notes_repository as repo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

notes_router = APIRouter(prefix="/notes", tags=["Notes"])
tags_router = APIRouter(prefix="/tags", tags=["Tags"])
search_router = APIRouter(prefix="/search", tags=["Search"])


# ---------------------------------------------------------------------------
# Notes endpoints
# ---------------------------------------------------------------------------

@notes_router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note",
    description="Create a new note with optional tags and Markdown flag.",
)
# PUBLIC_INTERFACE
def create_note(
    payload: NoteCreate,
    db: sqlite3.Connection = Depends(get_db),
) -> NoteResponse:
    """
    Create a note.

    - **title**: Note title (may be empty)
    - **content**: Note body (plain text or Markdown)
    - **is_markdown**: Set to true to treat content as Markdown
    - **tags**: List of tag names (created automatically if new)
    """
    note = repo.create_note(
        db,
        title=payload.title,
        content=payload.content,
        is_markdown=payload.is_markdown,
        tags=payload.tags,
    )
    return NoteResponse(**note)


@notes_router.get(
    "",
    response_model=NoteListResponse,
    summary="List notes",
    description="Retrieve a paginated list of notes, optionally filtered by tag.",
)
# PUBLIC_INTERFACE
def list_notes(
    skip: int = Query(default=0, ge=0, description="Number of items to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max items to return"),
    tag: Optional[str] = Query(default=None, description="Filter by tag name"),
    db: sqlite3.Connection = Depends(get_db),
) -> NoteListResponse:
    """
    List notes.

    Returns a paginated list ordered by last-updated descending.
    """
    result = repo.list_notes(db, skip=skip, limit=limit, tag=tag)
    return NoteListResponse(
        total=result["total"],
        items=[NoteResponse(**n) for n in result["items"]],
    )


@notes_router.get(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Get a note",
    description="Retrieve a single note by its ID.",
    responses={404: {"description": "Note not found"}},
)
# PUBLIC_INTERFACE
def get_note(
    note_id: int,
    db: sqlite3.Connection = Depends(get_db),
) -> NoteResponse:
    """Retrieve a single note by ID."""
    note = repo.get_note(db, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return NoteResponse(**note)


@notes_router.put(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Update a note",
    description="Update title, content, markdown flag, or tags of an existing note.",
    responses={404: {"description": "Note not found"}},
)
# PUBLIC_INTERFACE
def update_note(
    note_id: int,
    payload: NoteUpdate,
    db: sqlite3.Connection = Depends(get_db),
) -> NoteResponse:
    """
    Update a note.

    All fields are optional; only provided fields are changed.
    Supplying an empty tags list removes all tags.
    """
    note = repo.update_note(
        db,
        note_id=note_id,
        title=payload.title,
        content=payload.content,
        is_markdown=payload.is_markdown,
        tags=payload.tags,
    )
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return NoteResponse(**note)


@notes_router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a note",
    description="Permanently delete a note and its tag associations.",
    responses={404: {"description": "Note not found"}},
)
# PUBLIC_INTERFACE
def delete_note(
    note_id: int,
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a note by ID."""
    deleted = repo.delete_note(db, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")


# ---------------------------------------------------------------------------
# Tags endpoints
# ---------------------------------------------------------------------------

@tags_router.get(
    "",
    response_model=list[TagResponse],
    summary="List all tags",
    description="Retrieve all tags sorted alphabetically.",
)
# PUBLIC_INTERFACE
def list_tags(
    db: sqlite3.Connection = Depends(get_db),
) -> list[TagResponse]:
    """List all existing tags."""
    tags = repo.list_tags(db)
    return [TagResponse(**t) for t in tags]


@tags_router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tag",
    description="Delete a tag and remove it from all associated notes.",
    responses={404: {"description": "Tag not found"}},
)
# PUBLIC_INTERFACE
def delete_tag(
    tag_id: int,
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a tag by ID."""
    deleted = repo.delete_tag(db, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------

@search_router.get(
    "",
    response_model=NoteListResponse,
    summary="Search notes",
    description="Full-text search across note titles and content, with optional tag filter.",
)
# PUBLIC_INTERFACE
def search_notes(
    q: str = Query(..., min_length=1, description="Search query string"),
    tag: Optional[str] = Query(default=None, description="Filter by tag name"),
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    db: sqlite3.Connection = Depends(get_db),
) -> NoteListResponse:
    """
    Search notes using full-text search (FTS5).

    Falls back to LIKE-based search if FTS is unavailable.
    """
    result = repo.search_notes(db, query=q, tag=tag, skip=skip, limit=limit)
    return NoteListResponse(
        total=result["total"],
        items=[NoteResponse(**n) for n in result["items"]],
    )
