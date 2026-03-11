"""
Pydantic schemas for the Notes API.

These models define the data contracts for all request payloads and
response bodies. All public fields are documented.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tag schemas
# ---------------------------------------------------------------------------

class TagBase(BaseModel):
    """Base schema with common tag fields."""
    name: str = Field(..., min_length=1, max_length=50, description="Tag label (case-insensitive)")


class TagCreate(TagBase):
    """Schema for creating a new tag."""


class TagResponse(TagBase):
    """Schema returned for a tag resource."""
    id: int = Field(..., description="Unique tag identifier")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Note schemas
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    """Schema for creating a new note."""
    title: str = Field(default="", max_length=255, description="Note title")
    content: str = Field(default="", description="Note body; may contain Markdown")
    is_markdown: bool = Field(default=False, description="Whether the content is Markdown")
    tags: List[str] = Field(default_factory=list, description="List of tag names to attach")


class NoteUpdate(BaseModel):
    """Schema for partially updating an existing note (all fields optional)."""
    title: Optional[str] = Field(default=None, max_length=255, description="Updated title")
    content: Optional[str] = Field(default=None, description="Updated content")
    is_markdown: Optional[bool] = Field(default=None, description="Toggle Markdown mode")
    tags: Optional[List[str]] = Field(default=None, description="Replace tag list (full replacement)")


class NoteResponse(BaseModel):
    """Schema returned for a note resource."""
    id: int = Field(..., description="Unique note identifier")
    title: str = Field(..., description="Note title")
    content: str = Field(..., description="Note content")
    is_markdown: bool = Field(..., description="Whether content is Markdown")
    tags: List[str] = Field(default_factory=list, description="Tags attached to this note")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")

    model_config = {"from_attributes": True}


class NoteListResponse(BaseModel):
    """Paginated list of notes."""
    total: int = Field(..., description="Total matching notes (before pagination)")
    items: List[NoteResponse] = Field(..., description="Page of note resources")


class SearchQuery(BaseModel):
    """Schema for full-text search requests."""
    q: str = Field(..., min_length=1, description="Search query string")
    tag: Optional[str] = Field(default=None, description="Optional tag filter")
    skip: int = Field(default=0, ge=0, description="Offset for pagination")
    limit: int = Field(default=20, ge=1, le=100, description="Page size")


class HealthResponse(BaseModel):
    """API health check response."""
    status: str = Field(..., description="Service status ('ok')")
    message: str = Field(..., description="Human-readable status message")
