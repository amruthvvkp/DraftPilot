"""Test chunking, rank fusion, and the SQLite hybrid store (vector + full-text)."""

from pathlib import Path

import pytest
from _async import run_async

from draftpilot.core.rag import (
    HashEmbedder,
    IndexedDocument,
    SQLiteHybridIndex,
    chunk_text,
    reciprocal_rank_fusion,
)


def test_chunks_are_paragraph_aligned_bounded_and_carry_offsets() -> None:
    """Chunks respect the size limit, overlap slightly, and map back to the source text."""
    paragraphs = [f"Paragraph {n} " + "word " * 60 for n in range(8)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=700, overlap=100)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 700 for chunk in chunks)
    assert all(text[chunk.start : chunk.end] == chunk.text for chunk in chunks)
    assert chunks[0].start == 0 and chunks[-1].end == len(text.rstrip())
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_long_paragraphs_are_windowed_and_empty_text_has_no_chunks() -> None:
    """A single oversized paragraph is cut into windows; blank text yields nothing."""
    chunks = chunk_text("x" * 3_000, max_chars=1_000, overlap=100)
    assert len(chunks) >= 3 and all(len(chunk.text) <= 1_000 for chunk in chunks)
    assert chunk_text("   \n\n  ") == []


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    """An item ranked well by both lists beats items ranked by only one."""
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]])
    assert max(fused, key=fused.__getitem__) == "b"
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)


def _index(tmp_path: Path) -> SQLiteHybridIndex:
    """Return a fresh hybrid store with deterministic embeddings."""
    index = SQLiteHybridIndex(tmp_path / "rag.sqlite3", HashEmbedder(128))
    run_async(index.ensure_schema())
    return index


def test_hybrid_search_is_project_scoped_versioned_and_cited(tmp_path: Path) -> None:
    """Search only one project's chunks and cite source, version, and passage offsets."""
    index = _index(tmp_path)
    run_async(index.upsert(IndexedDocument(4, "scene:1", "scene", "EXT. RIVER - DAY\n\nEdward catches the enormous fish.", 2)))
    run_async(index.upsert(IndexedDocument(5, "scene:9", "scene", "Edward catches a fish in another project.", 1)))
    results = run_async(index.search(4, "Edward fish"))
    assert [result.citation.project_id for result in results] == [4]
    citation = results[0].citation
    assert (citation.source_id, citation.content_version, citation.start) == ("scene:1", 2, 0)
    assert citation.end == len("EXT. RIVER - DAY\n\nEdward catches the enormous fish.")


def test_upsert_replaces_a_source_and_delete_removes_it(tmp_path: Path) -> None:
    """Re-indexing a source replaces its chunks; deleting it removes them from search."""
    index = _index(tmp_path)
    run_async(index.upsert(IndexedDocument(4, "brief", "brief", "A storm arrives.", 1)))
    run_async(index.upsert(IndexedDocument(4, "brief", "brief", "A wedding begins.", 2)))
    assert run_async(index.search(4, "storm")) == [] or run_async(index.search(4, "storm"))[0].text != "A storm arrives."
    assert run_async(index.search(4, "wedding"))[0].citation.content_version == 2
    run_async(index.delete(4, "brief"))
    assert run_async(index.search(4, "wedding")) == []
    assert run_async(index.stats(4)) == {"chunks": 0, "documents": 0, "embedded_chunks": 0}


def test_search_degrades_to_full_text_when_embeddings_fail(tmp_path: Path) -> None:
    """If the embedding model is down, indexing and search still work lexically."""

    class Down(HashEmbedder):
        """Fail every embedding call like an unreachable model server."""

        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            """Raise like a connection error."""
            raise ConnectionError("LM Studio is not running")

        async def embed_query(self, text: str) -> list[float]:
            """Raise like a connection error."""
            raise ConnectionError("LM Studio is not running")

    index = SQLiteHybridIndex(tmp_path / "rag.sqlite3", Down(64))
    run_async(index.ensure_schema())
    run_async(index.upsert(IndexedDocument(4, "note", "note", "The witch's glass eye shows each death.", 1)))
    assert run_async(index.stats(4)) == {"chunks": 1, "documents": 1, "embedded_chunks": 0}
    assert run_async(index.search(4, "glass eye"))[0].citation.source_id == "note"


def test_semantic_ranking_finds_passages_without_shared_terms(tmp_path: Path) -> None:
    """With embeddings, a chunk can rank without any lexical overlap with the query."""

    class Topical(HashEmbedder):
        """Embed by topic so 'ocean' and 'sea' land together."""

        def _embed(self, text: str) -> list[float]:
            """Map water words to one axis and everything else to another."""
            water = any(word in text.casefold() for word in ("sea", "ocean", "river"))
            return [1.0, 0.0] + [0.0] * (self.dimensions - 2) if water else [0.0, 1.0] + [0.0] * (self.dimensions - 2)

    index = SQLiteHybridIndex(tmp_path / "rag.sqlite3", Topical(8))
    run_async(index.ensure_schema())
    run_async(index.upsert(IndexedDocument(4, "a", "scene", "Waves break against the old sea wall.", 1)))
    run_async(index.upsert(IndexedDocument(4, "b", "scene", "A circus tent goes up in the rain.", 1)))
    assert run_async(index.search(4, "ocean", limit=1))[0].citation.source_id == "a"
