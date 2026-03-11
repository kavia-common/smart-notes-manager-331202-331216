"""
Notes Manager — FastAPI application entry point.

Configures:
  - App metadata (title, description, version) for Swagger UI
  - CORS middleware
  - Database initialisation on startup (lifespan)
  - Route registration (notes, tags, search)
  - Health-check endpoint
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.database import init_db
from src.api.routes import notes_router, tags_router, search_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "info").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env if present
load_dotenv()

# ---------------------------------------------------------------------------
# App lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database schema on startup."""
    logger.info("Notes API starting up…")
    init_db()
    logger.info("Notes API ready")
    yield
    logger.info("Notes API shutting down")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

_DESCRIPTION = """
## Smart Notes Manager API

A REST API for creating, editing, deleting, listing, and searching notes.

### Features
* **Full CRUD** for notes (title, content, Markdown flag)
* **Tagging** — attach multiple tags per note; filter list/search by tag
* **Full-text search** via SQLite FTS5 (falls back to LIKE)
* **Pagination** on all list endpoints

### Quick start
1. `POST /notes` — create a note
2. `GET  /notes` — list notes (supports `?tag=` and `?skip=`/`?limit=`)
3. `GET  /search?q=...` — full-text search
4. `GET  /tags` — list all tags
"""

openapi_tags = [
    {
        "name": "Notes",
        "description": "Create, read, update, and delete notes.",
    },
    {
        "name": "Tags",
        "description": "Manage tags used to organise notes.",
    },
    {
        "name": "Search",
        "description": "Full-text search across notes.",
    },
    {
        "name": "Health",
        "description": "Service health check.",
    },
]

app = FastAPI(
    title="Smart Notes Manager API",
    description=_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
)

# ---------------------------------------------------------------------------
# CORS middleware — allow all origins in development
# ---------------------------------------------------------------------------

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:4000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Wide open; restrict per env if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(notes_router)
app.include_router(tags_router)
app.include_router(search_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get(
    "/",
    tags=["Health"],
    summary="Health check",
    description="Returns service status. Used by load balancers and readiness probes.",
    response_description="JSON with `status` and `message` fields.",
)
# PUBLIC_INTERFACE
def health_check():
    """
    Health check endpoint.

    Returns:
        dict: ``{"status": "ok", "message": "Healthy"}``
    """
    return {"status": "ok", "message": "Healthy"}


@app.get(
    "/healthz",
    tags=["Health"],
    summary="Kubernetes readiness probe",
    description="Alias health-check for Kubernetes readiness/liveness probes.",
)
# PUBLIC_INTERFACE
def healthz():
    """Kubernetes-style readiness probe."""
    return {"status": "ok"}
