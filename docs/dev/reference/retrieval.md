# Retrieval

Project-scoped hybrid retrieval. `draftpilot.core.rag` splits documents (scenes, story artifacts,
canon nodes, references, translations) into overlapping, paragraph-aware chunks with character
offsets, embeds them, and searches a vector index and a full-text index, fusing the two rankings
with reciprocal rank fusion. The store is Postgres (pgvector + tsvector) in the compose stack or
SQLite FTS5 locally and in tests (`RAG__BACKEND`); embeddings come from LM Studio by default
(`RAG__EMBEDDING_PROVIDER`). `draftpilot.core.rag_client` searches the separate RAG service over
HTTP, or an in-process index when one is bound (evals, offline tools).

::: draftpilot.core.rag

::: draftpilot.core.rag_client
