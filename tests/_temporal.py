"""Temporal test helpers: a time-skipping server and a worker on a throwaway task queue."""

import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


@asynccontextmanager
async def temporal_worker(
    workflows: Sequence[type], activities: Sequence[Callable[..., Any]]
) -> AsyncIterator[tuple[Client, str]]:
    """Yield a Pydantic AI-configured client and the task queue a worker is serving on."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        client = Client(**{**env.client.config(), "plugins": [PydanticAIPlugin()]})
        task_queue = f"test-{uuid.uuid4().hex}"
        async with Worker(client, task_queue=task_queue, workflows=list(workflows), activities=list(activities)):
            yield client, task_queue
