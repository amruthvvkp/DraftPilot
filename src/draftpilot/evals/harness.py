"""An isolated Big Fish project for evals: its own database, its own retrieval index, no side effects."""

import tempfile
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import draftpilot.models  # noqa: F401  (registers every table)
from draftpilot.core import rag_client
from draftpilot.core.config import LLMSettings, RAGSettings, settings
from draftpilot.core.db import database
from draftpilot.core.providers import build_chat_model
from draftpilot.core.rag import IndexedDocument, SQLiteHybridIndex, create_embedder
from draftpilot.core.rag_sources import project_documents
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.core.twins import refresh_story_twin
from draftpilot.crud import scenes as scenes_crud
from draftpilot.models import Project, Scene, Screenplay

BIG_FISH = Path(__file__).resolve().parents[3] / "tests" / "test_screenplays" / "Big-Fish.fountain"


class _NoRedis:
    """Swallow live-sync events so evals never touch a running studio."""

    async def publish(self, *_args: object) -> None:
        """Drop the event."""


async def _no_queue() -> Any:
    """Refuse background jobs so evals never enqueue work on a running stack."""
    raise ConnectionError("evals run without a queue")


@dataclass(frozen=True)
class EvalProject:
    """The seeded eval project and its scenes in script order."""

    project_id: int
    screenplay_id: int
    scenes: list[Scene]

    def scene(self, number: int) -> Scene:
        """Return the scene at a 1-based script position."""
        return self.scenes[number - 1]


def eval_llm(model: str = "") -> LLMSettings:
    """Return LM Studio settings for evals (``model`` empty means the chat model, else ``auto``)."""
    return LLMSettings(provider="lm_studio", base_url=settings.eval.base_url, model=model or settings.eval.chat_model or "auto")


async def eval_models() -> tuple[Any, str, Any, str]:
    """Return the chat model and the judge model, both on local LM Studio."""
    chat, chat_name = await build_chat_model(eval_llm())
    judge, judge_name = await build_chat_model(eval_llm(settings.eval.judge_model))
    return chat, chat_name, judge, judge_name


@asynccontextmanager
async def eval_project(*, embeddings: bool = True) -> AsyncIterator[EvalProject]:
    """Seed Big Fish into a throwaway SQLite database, index it locally, and bind the app to both."""
    workdir = Path(tempfile.mkdtemp(prefix="draftpilot-eval-"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{workdir / 'eval.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection: object, _record: object) -> None:
        """Enforce foreign keys like Postgres does."""
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    rag = RAGSettings(
        backend="sqlite",
        embedding_provider="lm_studio" if embeddings else "hash",
        embedding_base_url=settings.eval.base_url,
        embedding_model=settings.eval.embedding_model or settings.rag.embedding_model,
    )
    index = SQLiteHybridIndex(workdir / "rag.sqlite3", create_embedder(rag))
    with ExitStack() as stack:
        stack.enter_context(database.bound_to(engine))
        stack.enter_context(patch("draftpilot.core.events.get_redis", lambda: _NoRedis()))
        stack.enter_context(patch("draftpilot.core.queue.pool.get_arq_pool", _no_queue))
        stack.enter_context(rag_client.local_index(index))
        async with database.session_scope() as session:
            project = Project(title="Big Fish", logline="A son pieces together the truth behind his dying father's tall tales.")
            session.add(project)
            await session.flush()
            screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
            session.add(screenplay)
            await session.commit()
            await save_screenplay_doc(session, screenplay.id or 0, parse_fountain(BIG_FISH.read_text()))
            await refresh_story_twin(session, project.id or 0)
            await index.ensure_schema()
            for document in await project_documents(session, project.id or 0):
                await index.upsert(IndexedDocument(project_id=project.id or 0, **document))  # type: ignore[arg-type]
            scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0)
        try:
            yield EvalProject(project.id or 0, screenplay.id or 0, scenes)
        finally:
            await engine.dispose()
