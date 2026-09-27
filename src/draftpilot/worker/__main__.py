"""Run the Temporal worker: ``python -m draftpilot.worker``."""

import asyncio
import signal

import logfire
from temporalio.client import Client
from temporalio.worker import Worker

from draftpilot.core import telemetry, temporal
from draftpilot.core.config import settings
from draftpilot.core.db import dispose_engine
from draftpilot.worker.activities import ACTIVITIES
from draftpilot.worker.workflows import WORKFLOWS


def build_worker(client: Client) -> Worker:
    """Build the worker that serves every DraftPilot workflow and activity on the task queue."""
    return Worker(client, task_queue=settings.temporal.task_queue, workflows=WORKFLOWS, activities=ACTIVITIES)


async def main() -> None:
    """Connect, serve until SIGINT/SIGTERM, then shut down gracefully."""
    telemetry.setup(worker=True)
    client = await temporal.connect()
    worker = build_worker(client)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    logfire.info("Temporal worker serving {queue} on {host}", queue=settings.temporal.task_queue, host=settings.temporal.host)
    async with worker:
        await stop.wait()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
