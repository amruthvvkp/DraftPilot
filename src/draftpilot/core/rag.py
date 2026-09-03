"""Replaceable project-scoped retrieval primitives with citation-bearing results."""

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
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


class EmbeddingProvider(Protocol):
    """Define the replaceable text-to-vector retrieval contract."""

    def embed(self, text: str) -> list[float]:
        """Return a normalized vector for one text value."""


class HashEmbeddingProvider:
    """Provide deterministic local embeddings without a model download."""

    def __init__(self, dimensions: int = 128) -> None:
        """Configure the bounded vector dimensionality."""
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """Hash normalized terms into a deterministic unit vector."""
        vector = [0.0] * self.dimensions
        for term in text.casefold().split():
            digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


def create_embedding_provider(name: str) -> EmbeddingProvider | None:
    """Create a configured local provider or retain lexical-only behavior."""
    if name == "hash":
        return HashEmbeddingProvider()
    if name == "lexical":
        return None
    raise ValueError(f"Unsupported embedding provider: {name}")


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


class SQLiteLexicalIndex(LocalLexicalIndex):
    """Persist the local lexical index while retaining the vector-store contract."""

    def __init__(self, database_path: Path, embedding_provider: EmbeddingProvider | None = None) -> None:
        """Open or create the SQLite document store."""
        self.database_path = database_path
        self.embedding_provider = embedding_provider
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_documents (
                    project_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    content_version INTEGER NOT NULL,
                    PRIMARY KEY (project_id, source_id)
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(indexed_documents)")}
            if "embedding" not in columns:
                connection.execute("ALTER TABLE indexed_documents ADD COLUMN embedding TEXT")

    def _connect(self) -> sqlite3.Connection:
        """Create a short-lived connection for one store operation."""
        return sqlite3.connect(self.database_path)

    def upsert(self, document: IndexedDocument) -> None:
        """Insert or replace a document in the durable store."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO indexed_documents
                    (project_id, source_id, source_kind, text, content_version, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_id) DO UPDATE SET
                    source_kind = excluded.source_kind,
                    text = excluded.text,
                    content_version = excluded.content_version,
                    embedding = excluded.embedding
                """,
                (
                    document.project_id,
                    document.source_id,
                    document.source_kind,
                    document.text,
                    document.content_version,
                    json.dumps(self.embedding_provider.embed(document.text))
                    if self.embedding_provider
                    else None,
                ),
            )

    def delete(self, project_id: int, source_id: str) -> None:
        """Delete a document from the durable project partition."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM indexed_documents WHERE project_id = ? AND source_id = ?",
                (project_id, source_id),
            )

    def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Search durable documents without crossing project boundaries."""
        terms = {term.casefold() for term in query.split() if term.strip()}
        if not terms:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source_id, source_kind, text, content_version, embedding FROM indexed_documents WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        matches: list[RetrievalResult] = []
        query_vector = self.embedding_provider.embed(query) if self.embedding_provider else None
        for source_id, source_kind, text, content_version, stored_embedding in rows:
            if query_vector and stored_embedding:
                document_vector = json.loads(stored_embedding)
                score = sum(left * right for left, right in zip(query_vector, document_vector, strict=True))
            else:
                words = text.casefold().split()
                score = sum(word.strip(".,!?;:") in terms for word in words) / len(terms)
            if score:
                matches.append(
                    RetrievalResult(
                        text=text,
                        score=score,
                        citation=RetrievalCitation(
                            project_id=project_id,
                            source_id=source_id,
                            source_kind=source_kind,
                            content_version=content_version,
                        ),
                    )
                )
        return sorted(matches, key=lambda result: result.score, reverse=True)[:limit]
