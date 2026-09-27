"""Project-scoped hybrid retrieval: chunking, embeddings, and vector + full-text search.

Documents (scenes, story artifacts, canon nodes, references, translations) are split into
overlapping paragraph-aware chunks with character offsets. Each chunk is embedded (LM Studio
via PydanticAI's ``Embedder`` by default) and full-text indexed. A search runs a vector
ranking and a lexical ranking and fuses them with reciprocal-rank fusion (RRF), so exact names
and semantic matches both surface. Two interchangeable stores implement the same contract:
``PostgresHybridIndex`` (pgvector HNSW + tsvector GIN, production) and ``SQLiteHybridIndex``
(FTS5 + in-process cosine, tests and Postgres-less development).
"""

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import logfire
from pydantic import BaseModel, Field

RRF_K = 60


class RetrievalCitation(BaseModel):
    """Identify the versioned source (and the passage within it) supporting a result."""

    project_id: int
    source_id: str
    source_kind: str
    content_version: int = Field(ge=1)
    chunk_index: int = 0
    start: int = 0
    end: int = 0


class RetrievalResult(BaseModel):
    """Return one retrieved passage with its fused score and citation."""

    text: str
    score: float
    citation: RetrievalCitation


@dataclass(frozen=True)
class IndexedDocument:
    """Hold one project document to index."""

    project_id: int
    source_id: str
    source_kind: str
    text: str
    content_version: int


@dataclass(frozen=True)
class Chunk:
    """A passage of a document with its character offsets."""

    index: int
    start: int
    end: int
    text: str


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of each blank-line-separated paragraph, whitespace-trimmed."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for separator in [*re.finditer(r"\n[ \t]*\n\s*", text), None]:
        stop = separator.start() if separator else len(text)
        block = text[cursor:stop]
        if block.strip():
            start = cursor + (len(block) - len(block.lstrip()))
            spans.append((start, cursor + len(block.rstrip())))
        cursor = separator.end() if separator else len(text)
    return spans


def chunk_text(text: str, max_chars: int = 1_200, overlap: int = 150) -> list[Chunk]:
    """Split text into paragraph-aligned chunks of at most ``max_chars`` with a small overlap."""
    if max_chars <= overlap:
        raise ValueError("max_chars must exceed overlap")
    if not text.strip():
        return []
    paragraphs = _paragraph_spans(text)
    chunks: list[Chunk] = []
    start = paragraphs[0][0] if paragraphs else 0
    end = start
    for p_start, p_end in paragraphs:
        if p_end - start <= max_chars:
            end = p_end
            continue
        if end > start:
            chunks.append(Chunk(len(chunks), start, end, text[start:end]))
            start = max(p_start, end - overlap) if end - overlap > start else p_start
        # A single paragraph longer than max_chars is cut into windows.
        while p_end - start > max_chars:
            cut = text.rfind(" ", start, start + max_chars)
            cut = cut if cut > start + max_chars // 2 else start + max_chars
            chunks.append(Chunk(len(chunks), start, cut, text[start:cut]))
            start = max(cut - overlap, start + 1)
        end = p_end
    if end > start:
        chunks.append(Chunk(len(chunks), start, end, text[start:end]))
    return chunks


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Any]], k: int = RRF_K) -> dict[Any, float]:
    """Fuse ranked candidate lists: each appearance at rank r contributes 1 / (k + r)."""
    scores: dict[Any, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


class TextEmbedder(Protocol):
    """Embed documents and queries into vectors of a fixed dimensionality."""

    name: str
    dimensions: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per document text."""

    async def embed_query(self, text: str) -> list[float]:
        """Return the vector for one search query."""


class HashEmbedder:
    """Deterministic offline embeddings (hashed terms); for tests and air-gapped installs."""

    def __init__(self, dimensions: int = 256) -> None:
        """Configure the vector dimensionality."""
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least 8")
        self.dimensions = dimensions
        self.name = f"hash-{dimensions}"

    def _embed(self, text: str) -> list[float]:
        """Hash normalized terms into a unit vector."""
        vector = [0.0] * self.dimensions
        for term in re.findall(r"\w+", text.casefold()):
            digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed every document text."""
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        """Embed one query."""
        return self._embed(text)


class ModelEmbedder:
    """Embed through a PydanticAI ``Embedder`` on an OpenAI-compatible server (LM Studio)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        dimensions: int,
        api_key: str = "",
        document_prefix: str = "",
        query_prefix: str = "",
    ) -> None:
        """Configure the embedding model, endpoint, and task prefixes (e.g. nomic's)."""
        from pydantic_ai import Embedder
        from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
        from pydantic_ai.providers.openai import OpenAIProvider

        self.name = model
        self.dimensions = dimensions
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix
        provider = OpenAIProvider(base_url=base_url, api_key=api_key or "lm-studio")
        self._embedder = Embedder(OpenAIEmbeddingModel(model, provider=provider))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents in batches, prefixing each for asymmetric retrieval models."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = [self.document_prefix + text for text in texts[start : start + 32]]
            result = await self._embedder.embed_documents(batch)
            vectors.extend([list(map(float, vector)) for vector in result.embeddings])
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Embed one query with the query prefix."""
        result = await self._embedder.embed_query(self.query_prefix + text)
        return list(map(float, result.embeddings[0]))


class HybridIndex(Protocol):
    """The contract both retrieval stores implement."""

    async def ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""

    async def upsert(self, document: IndexedDocument) -> int:
        """Replace a document's chunks; return how many chunks were stored."""

    async def delete(self, project_id: int, source_id: str) -> None:
        """Remove a document's chunks."""

    async def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Return fused hybrid results from one project."""

    async def stats(self, project_id: int) -> dict[str, int]:
        """Return chunk and document counts for one project."""


async def _embed_or_none(embedder: TextEmbedder | None, texts: list[str]) -> list[list[float]] | None:
    """Embed texts, degrading to lexical-only indexing when the model is unavailable."""
    if embedder is None or not texts:
        return None
    try:
        return await embedder.embed_documents(texts)
    except Exception as exc:  # noqa: BLE001 - retrieval must keep working without embeddings
        logfire.warning("Embedding skipped; indexing lexically only: {exc}", exc=str(exc))
        return None


async def _query_vector(embedder: TextEmbedder | None, query: str) -> list[float] | None:
    """Embed a query, or return ``None`` so search falls back to full-text only."""
    if embedder is None:
        return None
    try:
        return await embedder.embed_query(query)
    except Exception as exc:  # noqa: BLE001 - search must keep working without embeddings
        logfire.warning("Query embedding skipped; searching lexically only: {exc}", exc=str(exc))
        return None


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the cosine similarity of two vectors."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _fts_query(query: str) -> str:
    """Turn free text into an OR query of quoted terms that FTS5 accepts safely."""
    terms = [term for term in re.findall(r"\w+", query.casefold()) if len(term) > 1]
    return " OR ".join(f'"{term}"' for term in terms[:32])


class SQLiteHybridIndex:
    """Hybrid index in one SQLite file: FTS5 for lexical ranking, stored vectors for cosine."""

    def __init__(self, database_path: Path, embedder: TextEmbedder | None = None) -> None:
        """Remember the database file and the (optional) embedder."""
        self.database_path = database_path
        self.embedder = embedder

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.database_path)

    async def ensure_schema(self) -> None:
        """Create the chunk table and its FTS5 mirror."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_chunk (
                    project_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    content_version INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding TEXT,
                    embedding_model TEXT,
                    PRIMARY KEY (project_id, source_id, chunk_index)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunk_fts USING fts5(
                    text, project_id UNINDEXED, source_id UNINDEXED, chunk_index UNINDEXED
                );
                """
            )

    async def upsert(self, document: IndexedDocument) -> int:
        """Replace a document's chunks, embedding them when the model is available."""
        chunks = chunk_text(document.text)
        vectors = await _embed_or_none(self.embedder, [chunk.text for chunk in chunks])
        model = self.embedder.name if vectors is not None and self.embedder else None
        with self._connect() as connection:
            self._delete(connection, document.project_id, document.source_id)
            for position, chunk in enumerate(chunks):
                connection.execute(
                    "INSERT INTO rag_chunk VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        document.project_id, document.source_id, document.source_kind, chunk.index,
                        chunk.start, chunk.end, document.content_version, chunk.text,
                        json.dumps(vectors[position]) if vectors else None, model,
                    ),
                )
                connection.execute(
                    "INSERT INTO rag_chunk_fts (text, project_id, source_id, chunk_index) VALUES (?, ?, ?, ?)",
                    (chunk.text, document.project_id, document.source_id, chunk.index),
                )
        return len(chunks)

    @staticmethod
    def _delete(connection: sqlite3.Connection, project_id: int, source_id: str) -> None:
        """Delete a document's rows from both tables."""
        connection.execute("DELETE FROM rag_chunk WHERE project_id = ? AND source_id = ?", (project_id, source_id))
        connection.execute("DELETE FROM rag_chunk_fts WHERE project_id = ? AND source_id = ?", (project_id, source_id))

    async def delete(self, project_id: int, source_id: str) -> None:
        """Remove a document's chunks."""
        with self._connect() as connection:
            self._delete(connection, project_id, source_id)

    async def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Fuse the FTS5 BM25 ranking with the cosine ranking over this project's chunks."""
        pool = max(limit * 4, 20)
        vector = await _query_vector(self.embedder, query)
        with self._connect() as connection:
            rows = {
                (row[0], row[1]): row
                for row in connection.execute(
                    "SELECT source_id, chunk_index, source_kind, start_offset, end_offset, content_version, text, "
                    "embedding, embedding_model FROM rag_chunk WHERE project_id = ?",
                    (project_id,),
                )
            }
            fts = _fts_query(query)
            lexical = (
                [
                    (row[0], row[1])
                    for row in connection.execute(
                        "SELECT source_id, chunk_index FROM rag_chunk_fts WHERE rag_chunk_fts MATCH ? "
                        "AND project_id = ? ORDER BY bm25(rag_chunk_fts) LIMIT ?",
                        (fts, project_id, pool),
                    )
                ]
                if fts
                else []
            )
        semantic: list[tuple[str, int]] = []
        if vector is not None and self.embedder is not None:
            scored = [
                (_cosine(vector, json.loads(row[7])), key)
                for key, row in rows.items()
                if row[7] and row[8] == self.embedder.name
            ]
            semantic = [key for _score, key in sorted(scored, reverse=True)[:pool]]
        fused = reciprocal_rank_fusion([lexical, semantic])
        results = []
        for key, score in sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]:
            source_id, chunk_index, source_kind, start, end, version, text, _embedding, _model = rows[key]
            results.append(
                RetrievalResult(
                    text=text,
                    score=round(score, 6),
                    citation=RetrievalCitation(
                        project_id=project_id, source_id=source_id, source_kind=source_kind,
                        content_version=version, chunk_index=chunk_index, start=start, end=end,
                    ),
                )
            )
        return results

    async def stats(self, project_id: int) -> dict[str, int]:
        """Return chunk, document, and embedded-chunk counts."""
        with self._connect() as connection:
            chunks, documents, embedded = connection.execute(
                "SELECT count(*), count(DISTINCT source_id), count(embedding) FROM rag_chunk WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return {"chunks": chunks, "documents": documents, "embedded_chunks": embedded}


def _vector_literal(vector: Sequence[float]) -> str:
    """Encode a vector as a pgvector text literal."""
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"


class PostgresHybridIndex:
    """Hybrid index in Postgres: pgvector HNSW (cosine) plus a generated tsvector with GIN."""

    def __init__(self, dsn: str, embedder: TextEmbedder | None, dimensions: int, schema: str = "rag") -> None:
        """Remember the connection string, embedder, vector dimensionality, and schema name."""
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid RAG schema name")
        self.dsn = dsn
        self.embedder = embedder
        self.dimensions = dimensions
        self.schema = schema
        self._pool: Any = None

    async def _connection_pool(self) -> Any:
        """Create the asyncpg pool on first use."""
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ensure_schema(self) -> None:
        """Create the pgvector extension, chunk table, and HNSW + GIN indexes."""
        pool = await self._connection_pool()
        async with pool.acquire() as connection:
            await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            await connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.chunk (
                    project_id integer NOT NULL,
                    source_id text NOT NULL,
                    source_kind text NOT NULL,
                    chunk_index integer NOT NULL,
                    start_offset integer NOT NULL,
                    end_offset integer NOT NULL,
                    content_version integer NOT NULL,
                    text text NOT NULL,
                    embedding vector({self.dimensions}),
                    embedding_model text,
                    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
                    PRIMARY KEY (project_id, source_id, chunk_index)
                )
                """
            )
            await connection.execute(
                f"CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw ON {self.schema}.chunk "
                "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
            )
            await connection.execute(f"CREATE INDEX IF NOT EXISTS chunk_tsv_gin ON {self.schema}.chunk USING gin (tsv)")
            await connection.execute(f"CREATE INDEX IF NOT EXISTS chunk_project ON {self.schema}.chunk (project_id)")

    async def upsert(self, document: IndexedDocument) -> int:
        """Replace a document's chunks in one transaction, embedding them when possible."""
        chunks = chunk_text(document.text)
        vectors = await _embed_or_none(self.embedder, [chunk.text for chunk in chunks])
        model = self.embedder.name if vectors is not None and self.embedder else None
        pool = await self._connection_pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                f"DELETE FROM {self.schema}.chunk WHERE project_id = $1 AND source_id = $2", document.project_id, document.source_id
            )
            await connection.executemany(
                f"INSERT INTO {self.schema}.chunk (project_id, source_id, source_kind, chunk_index, start_offset, end_offset, "
                "content_version, text, embedding, embedding_model) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::vector,$10)",
                [
                    (
                        document.project_id, document.source_id, document.source_kind, chunk.index, chunk.start,
                        chunk.end, document.content_version, chunk.text,
                        _vector_literal(vectors[position]) if vectors else None, model,
                    )
                    for position, chunk in enumerate(chunks)
                ],
            )
        return len(chunks)

    async def delete(self, project_id: int, source_id: str) -> None:
        """Remove a document's chunks."""
        pool = await self._connection_pool()
        async with pool.acquire() as connection:
            await connection.execute(f"DELETE FROM {self.schema}.chunk WHERE project_id = $1 AND source_id = $2", project_id, source_id)

    async def search(self, project_id: int, query: str, limit: int = 8) -> list[RetrievalResult]:
        """Fuse a full-text ranking (ts_rank_cd) with an HNSW cosine ranking, both project-scoped."""
        pool_size = max(limit * 4, 20)
        vector = await _query_vector(self.embedder, query)
        pool = await self._connection_pool()
        async with pool.acquire() as connection:
            lexical = await connection.fetch(
                f"SELECT source_id, chunk_index FROM {self.schema}.chunk, websearch_to_tsquery('simple', $2) q "
                "WHERE project_id = $1 AND tsv @@ q ORDER BY ts_rank_cd(tsv, q) DESC LIMIT $3",
                project_id, query, pool_size,
            )
            if not lexical:
                # websearch syntax is AND-like; retry with any-term matching for recall.
                terms = " | ".join(re.findall(r"\w+", query.casefold())[:32])
                lexical = await connection.fetch(
                    f"SELECT source_id, chunk_index FROM {self.schema}.chunk, to_tsquery('simple', $2) q "
                    "WHERE project_id = $1 AND tsv @@ q ORDER BY ts_rank_cd(tsv, q) DESC LIMIT $3",
                    project_id, terms or "''", pool_size,
                ) if terms else []
            semantic = (
                await connection.fetch(
                    f"SELECT source_id, chunk_index FROM {self.schema}.chunk WHERE project_id = $1 AND embedding_model = $2 "
                    "ORDER BY embedding <=> $3::vector LIMIT $4",
                    project_id, self.embedder.name if self.embedder else "", _vector_literal(vector), pool_size,
                )
                if vector is not None
                else []
            )
            fused = reciprocal_rank_fusion(
                [[(row["source_id"], row["chunk_index"]) for row in lexical],
                 [(row["source_id"], row["chunk_index"]) for row in semantic]]
            )
            top = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]
            if not top:
                return []
            rows = await connection.fetch(
                "SELECT source_id, chunk_index, source_kind, start_offset, end_offset, content_version, text "
                f"FROM {self.schema}.chunk WHERE project_id = $1 AND (source_id, chunk_index) IN "
                "(SELECT * FROM unnest($2::text[], $3::int[]))",
                project_id, [key[0] for key, _ in top], [key[1] for key, _ in top],
            )
        by_key = {(row["source_id"], row["chunk_index"]): row for row in rows}
        return [
            RetrievalResult(
                text=by_key[key]["text"],
                score=round(score, 6),
                citation=RetrievalCitation(
                    project_id=project_id, source_id=key[0], source_kind=by_key[key]["source_kind"],
                    content_version=by_key[key]["content_version"], chunk_index=key[1],
                    start=by_key[key]["start_offset"], end=by_key[key]["end_offset"],
                ),
            )
            for key, score in top
            if key in by_key
        ]

    async def stats(self, project_id: int) -> dict[str, int]:
        """Return chunk, document, and embedded-chunk counts."""
        pool = await self._connection_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT count(*) AS chunks, count(DISTINCT source_id) AS documents, count(embedding) AS embedded "
                f"FROM {self.schema}.chunk WHERE project_id = $1",
                project_id,
            )
        return {"chunks": row["chunks"], "documents": row["documents"], "embedded_chunks": row["embedded"]}


def create_embedder(settings: Any) -> TextEmbedder | None:
    """Build the configured embedder: ``lm_studio``/``openai_compatible``, ``hash``, or ``none``."""
    provider = settings.embedding_provider
    if provider in {"lexical", "none"}:
        return None
    if provider == "hash":
        return HashEmbedder(settings.embedding_dimensions)
    if provider in {"lm_studio", "openai_compatible"}:
        return ModelEmbedder(
            settings.embedding_model,
            settings.embedding_base_url,
            settings.embedding_dimensions,
            api_key=settings.embedding_api_key.get_secret_value(),
            document_prefix=settings.embedding_document_prefix,
            query_prefix=settings.embedding_query_prefix,
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


def create_index(settings: Any) -> HybridIndex:
    """Build the configured hybrid store (``postgres`` or ``sqlite``)."""
    embedder = create_embedder(settings)
    if settings.backend == "postgres":
        return PostgresHybridIndex(settings.database_url.get_secret_value(), embedder, settings.embedding_dimensions)
    if settings.backend == "sqlite":
        return SQLiteHybridIndex(settings.database_path, embedder)
    raise ValueError(f"Unsupported RAG backend: {settings.backend}")
