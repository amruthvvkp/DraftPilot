"""Discover a local LM Studio server and its loaded models for Tier 1 tests."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LMStudio:
    """Describe the reachable local LM Studio server and its loaded models."""

    base_url: str
    chat_models: list[str]
    embedding_models: list[str]


def discover_lmstudio(base_url: str) -> LMStudio:
    """Query LM Studio for loaded chat and embedding models."""
    root = base_url.removesuffix("/").removesuffix("/v1")
    with httpx.Client(timeout=5.0) as client:
        try:
            native = client.get(f"{root}/api/v0/models")
            native.raise_for_status()
            # Loaded models first, so tests never block on a just-in-time model load.
            entries = sorted(native.json().get("data", []), key=lambda m: m.get("state") != "loaded")
            chat = [m["id"] for m in entries if m.get("type") in {"llm", "vlm"}]
            embedding = [m["id"] for m in entries if m.get("type") == "embeddings"]
        except (httpx.HTTPError, ValueError):
            response = client.get(f"{root}/v1/models")
            response.raise_for_status()
            ids = [m["id"] for m in response.json().get("data", [])]
            embedding = [i for i in ids if "embed" in i.lower()]
            chat = [i for i in ids if i not in embedding]
    return LMStudio(base_url=f"{root}/v1", chat_models=chat, embedding_models=embedding)
