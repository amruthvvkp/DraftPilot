"""Expose project-scoped local retrieval over a small HTTP service."""

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from draftpilot.core.config import settings
from draftpilot.core.rag import IndexedDocument, LocalLexicalIndex, RetrievalResult

app = FastAPI(title="DraftPilot RAG", version=settings.metadata.version)
index = LocalLexicalIndex()


class DocumentRequest(BaseModel):
    """Describe one versioned document to index."""

    source_id: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=100_000)
    content_version: int = Field(ge=1)


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
def health() -> dict[str, str]:
    """Report service readiness without exposing indexed content."""
    return {"status": "ok"}


@app.post("/projects/{project_id}/documents", status_code=status.HTTP_204_NO_CONTENT)
def upsert_document(
    project_id: int,
    document: DocumentRequest,
    authorization: str | None = Header(default=None),
) -> None:
    """Upsert one document into its project partition."""
    _authorize(authorization)
    index.upsert(
        IndexedDocument(
            project_id=project_id,
            source_id=document.source_id,
            source_kind=document.source_kind,
            text=document.text,
            content_version=document.content_version,
        )
    )


@app.delete("/projects/{project_id}/documents/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    project_id: int,
    source_id: str,
    authorization: str | None = Header(default=None),
) -> None:
    """Delete one document from its project partition."""
    _authorize(authorization)
    index.delete(project_id, source_id)


@app.post("/projects/{project_id}/search", response_model=SearchResponse)
def search_project(
    project_id: int,
    query: SearchRequest,
    authorization: str | None = Header(default=None),
) -> SearchResponse:
    """Search only documents belonging to the requested project."""
    _authorize(authorization)
    limit = min(query.limit, settings.rag.max_results)
    return SearchResponse(results=index.search(project_id, query.query, limit))
