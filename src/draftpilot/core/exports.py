"""Persist bounded screenplay export artifacts in the local project volume."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class ExportError(ValueError):
    """Signal an invalid or unwritable export artifact."""


@dataclass(frozen=True)
class ExportArtifact:
    """Describe one atomically persisted screenplay export."""

    filename: str
    format: str
    bytes: int
    sha256: str


def _safe_name(label: str) -> str:
    """Normalize a screenplay title for a confined export filename."""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-.")
    return normalized[:80] or "screenplay"


def write_export(
    root: Path,
    project_id: int,
    screenplay_id: int,
    title: str,
    file_format: str,
    content: bytes,
    max_bytes: int,
) -> ExportArtifact:
    """Atomically write one bounded export beneath the configured local volume."""
    if project_id < 1 or screenplay_id < 1 or file_format not in {"fountain", "fdx", "pdf"}:
        raise ExportError("Invalid export identity or format")
    if not content or len(content) > max_bytes:
        raise ExportError("Export is empty or exceeds the configured size limit")
    directory = (root / "exports").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"{_safe_name(title)}-{project_id}-{screenplay_id}-{timestamp}.{file_format}"
    target = (directory / filename).resolve()
    if target.parent != directory:
        raise ExportError("Export path escaped its configured directory")
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ExportError("Unable to write export artifact") from exc
    return ExportArtifact(
        filename=filename,
        format=file_format,
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
