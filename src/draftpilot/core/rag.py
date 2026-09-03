"""Replaceable project-scoped retrieval primitives with citation-bearing results."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field


class RetrievalCitation(BaseModel):
    """Identify the versioned artifact supporting a retrieval result."""

    project_id: int
    source_id: str
    source_kind: str
    content_version: int = Field(ge=1)


class RetrievalResult(BaseModel):
    """Return retrieved text with its project-scoped citation."""

    text: str
    score: float
    citation: RetrievalCitation


@dataclass(frozen=True)
class IndexedDocument:
    """Hold one indexed project document."""

    project_id: int
    source_id: str
    source_kind: str
    text: str
    content_version: int


class VectorStore(Protocol):
    """Define the replaceable storage contract for retrieval documents."""

    def upsert(self, document: IndexedDocument) -> None:
        """Insert or replace one indexed document."""

    def delete(self, project_id: int, source_id: str) -> None:
        """Delete one project-scoped indexed document."""

    def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Search indexed documents within one project."""


class LocalLexicalIndex:
    """Provide a dependency-free local-first index behind the vector-store contract."""

    def __init__(self) -> None:
        """Initialize an empty local index."""
        self._documents: dict[tuple[int, str], IndexedDocument] = {}

    def upsert(self, document: IndexedDocument) -> None:
        """Insert or replace a document by project and source identifier."""
        self._documents[(document.project_id, document.source_id)] = document

    def delete(self, project_id: int, source_id: str) -> None:
        """Delete a document without affecting another project with the same source id."""
        self._documents.pop((project_id, source_id), None)

    def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Return lexical matches with citations, restricted to one project."""
        terms = {term.casefold() for term in query.split() if term.strip()}
        if not terms:
            return []
        matches: list[RetrievalResult] = []
        for document in self._documents.values():
            if document.project_id != project_id:
                continue
            words = document.text.casefold().split()
            score = sum(word.strip(".,!?;:") in terms for word in words) / len(terms)
            if score:
                matches.append(
                    RetrievalResult(
                        text=document.text,
                        score=score,
                        citation=RetrievalCitation(
                            project_id=document.project_id,
                            source_id=document.source_id,
                            source_kind=document.source_kind,
                            content_version=document.content_version,
                        ),
                    )
                )
        return sorted(matches, key=lambda result: result.score, reverse=True)[:limit]
