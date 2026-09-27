"""Test project-scoped incremental local retrieval."""

from draftpilot.core.rag import (
    HashEmbeddingProvider,
    IndexedDocument,
    LocalLexicalIndex,
    SQLiteLexicalIndex,
)


def test_retrieval_returns_versioned_citations_with_project_isolation() -> None:
    """Search only the requested project and preserve the source version."""
    index = LocalLexicalIndex()
    index.upsert(IndexedDocument(4, "outline-1", "outline", "A family returns home", 2))
    index.upsert(IndexedDocument(5, "outline-2", "outline", "A family leaves town", 1))
    results = index.search(4, "family home")
    assert len(results) == 1
    assert results[0].citation.project_id == 4
    assert results[0].citation.content_version == 2


def test_upsert_and_delete_refresh_one_source_incrementally() -> None:
    """Replace and remove one source without rebuilding unrelated documents."""
    index = LocalLexicalIndex()
    index.upsert(IndexedDocument(4, "brief-1", "brief", "A storm arrives", 1))
    index.upsert(IndexedDocument(4, "brief-1", "brief", "A wedding begins", 2))
    assert index.search(4, "wedding")[0].citation.content_version == 2
    index.delete(4, "brief-1")
    assert index.search(4, "wedding") == []


def test_sqlite_index_persists_replaceable_local_embeddings(tmp_path) -> None:
    """Persist local vectors while retaining project-scoped citations."""
    index = SQLiteLexicalIndex(tmp_path / "vectors.sqlite3", HashEmbeddingProvider())
    index.upsert(IndexedDocument(7, "scene:1", "scene", "a lantern in the house", 3))
    reopened = SQLiteLexicalIndex(tmp_path / "vectors.sqlite3", HashEmbeddingProvider())
    results = reopened.search(7, "lantern house")
    assert results
    assert results[0].citation.source_id == "scene:1"
    assert results[0].citation.content_version == 3
