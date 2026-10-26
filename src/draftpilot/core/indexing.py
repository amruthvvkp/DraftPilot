"""Best-effort RAG index maintenance after committed changes."""

from draftpilot.core import temporal


async def index_document(project_id: int, source_id: str, source_kind: str, text: str, content_version: int) -> None:
    """Queue a canonical document refresh; never fails the committed write."""
    await temporal.start_best_effort(
        "index_rag_document",
        {
            "project_id": project_id,
            "source_id": source_id,
            "source_kind": source_kind,
            "text": text,
            "content_version": content_version,
        },
        description="RAG indexing enqueue",
    )


async def delete_document(project_id: int, source_id: str) -> None:
    """Queue removal of one indexed document."""
    await temporal.start_best_effort(
        "delete_rag_document",
        {"project_id": project_id, "source_id": source_id},
        description="RAG deletion enqueue",
    )
