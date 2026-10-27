"""Expose project-scoped hybrid retrieval over a small, replaceable HTTP service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from draftpilot.core.config import settings
from draftpilot.core.rag import (
    HybridIndex,
    IndexedDocument,
    RetrievalResult,
    create_index,
)

index: HybridIndex = create_index(settings.rag)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create the store's schema on startup and release connections on shutdown."""
    await index.ensure_schema()
    try:
        yield
    finally:
        close = getattr(index, "close", None)
        if close is not None:
            await close()


app = FastAPI(title="DraftPilot RAG", version=settings.metadata.version, lifespan=lifespan)


class DocumentRequest(BaseModel):
    """Describe one versioned document to index."""

    source_id: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=500_000)
    content_version: int = Field(ge=1)


class DocumentResponse(BaseModel):
    """Report how a document was indexed."""

    chunks: int


class SearchRequest(BaseModel):
    """Describe a bounded project retrieval query."""

    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=8, ge=1, le=50)


class SearchResponse(BaseModel):
    """Return citation-bearing retrieval results."""

    results: list[RetrievalResult]


def _authorize(authorization: str | None) -> None:
    """Require the configured service bearer token."""
    expected = settings.rag.auth_token.get_secret_value()
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
async def health() -> dict[str, str]:
    """Report service readiness without exposing indexed content."""
    return {"status": "ok", "backend": settings.rag.backend, "embeddings": settings.rag.embedding_provider}


@app.post("/projects/{project_id}/documents", response_model=DocumentResponse)
async def upsert_document(
    project_id: int, document: DocumentRequest, authorization: str | None = Header(default=None)
) -> DocumentResponse:
    """Chunk, embed, and index one document in its project partition."""
    _authorize(authorization)
    chunks = await index.upsert(
        IndexedDocument(
            project_id=project_id,
            source_id=document.source_id,
            source_kind=document.source_kind,
            text=document.text,
            content_version=document.content_version,
        )
    )
    return DocumentResponse(chunks=chunks)


@app.delete("/projects/{project_id}/documents/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(project_id: int, source_id: str, authorization: str | None = Header(default=None)) -> None:
    """Delete one document from its project partition."""
    _authorize(authorization)
    await index.delete(project_id, source_id)


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_project(project_id: int, authorization: str | None = Header(default=None)) -> None:
    """Delete every indexed document of a deleted project."""
    _authorize(authorization)
    await index.purge(project_id)


@app.post("/projects/{project_id}/search", response_model=SearchResponse)
async def search_project(
    project_id: int, query: SearchRequest, authorization: str | None = Header(default=None)
) -> SearchResponse:
    """Hybrid-search only documents belonging to the requested project."""
    _authorize(authorization)
    limit = min(query.limit, settings.rag.max_results)
    return SearchResponse(results=await index.search(project_id, query.query, limit))


@app.get("/projects/{project_id}/stats")
async def project_stats(project_id: int, authorization: str | None = Header(default=None)) -> dict[str, int]:
    """Report how much of a project is indexed and embedded."""
    _authorize(authorization)
    return await index.stats(project_id)
