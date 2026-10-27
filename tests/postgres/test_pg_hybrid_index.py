"""Opt-in tier: the pgvector hybrid store against the local stack's Postgres (``-m postgres``)."""

import uuid

import pytest
from _async import run_async

from draftpilot.core.config import settings
from draftpilot.core.rag import HashEmbedder, IndexedDocument, PostgresHybridIndex

pytestmark = pytest.mark.postgres


def test_postgres_hybrid_search_is_scoped_cited_and_replaceable() -> None:
    """Upsert, search (HNSW + tsvector + RRF), replace, and delete in real Postgres."""
    schema = f"rag_test_{uuid.uuid4().hex[:10]}"
    index = PostgresHybridIndex(settings.rag.database_url.get_secret_value(), HashEmbedder(64), 64, schema=schema)

    async def scenario() -> None:
        """Run the whole store lifecycle on one event loop (asyncpg pools are loop-bound)."""
        try:
            await index.ensure_schema()
        except OSError as exc:
            pytest.fail(f"Local Postgres is not reachable ({exc}); start the stack or set RAG__DATABASE_URL")
        try:
            await index.upsert(IndexedDocument(4, "scene:47", "scene", "KARL THE GIANT is bigger than any man.", 1))
            await index.upsert(IndexedDocument(4, "scene:55", "scene", "All of these people are barefoot.", 1))
            await index.upsert(IndexedDocument(5, "scene:1", "scene", "Karl the giant in another project.", 1))
            results = await index.search(4, "Karl the giant")
            assert results[0].citation.source_id == "scene:47"
            assert {result.citation.project_id for result in results} == {4}
            assert await index.stats(4) == {"chunks": 2, "documents": 2, "embedded_chunks": 2}
            await index.upsert(IndexedDocument(4, "scene:47", "scene", "Karl leaves the cave.", 2))
            assert (await index.search(4, "Karl"))[0].citation.content_version == 2
            await index.delete(4, "scene:47")
            assert all(result.citation.source_id != "scene:47" for result in await index.search(4, "Karl"))
        finally:
            pool = await index._connection_pool()
            async with pool.acquire() as connection:
                await connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await index.close()

    run_async(scenario())
