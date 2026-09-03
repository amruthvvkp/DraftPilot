"""Small async test helpers that work with sync and browser pytest plugins."""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


def run_async(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine even when the calling test thread owns an event loop."""
    result: list[Any] = []
    error: list[BaseException] = []

    def runner() -> None:
        """Run the coroutine on an isolated event loop in a worker thread."""
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0] if result else None
