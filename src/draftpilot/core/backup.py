"""Create and validate confined, versioned DraftPilot backup archives."""

import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

BACKUP_SCHEMA_VERSION = 1


class BackupManifest(BaseModel):
    """Describe the identity and integrity of one backup archive."""

    schema_version: int = Field(default=BACKUP_SCHEMA_VERSION, ge=1)
    project_id: int = Field(ge=1)
    created_at: datetime
    app_version: str = Field(min_length=1, max_length=40)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BackupEnvelope(BaseModel):
    """Contain a backup manifest and its serialized project payload."""

    manifest: BackupManifest
    payload: dict[str, Any]


class BackupError(ValueError):
    """Signal an invalid, unsafe, or corrupt backup archive."""


def _confined_path(root: Path, candidate: Path) -> Path:
    """Resolve a backup path and reject paths outside the configured root."""
    resolved_root = root.expanduser().resolve()
    resolved_candidate = candidate.expanduser().resolve()
    if resolved_candidate.parent != resolved_root:
        raise BackupError("Backup path must remain inside the configured backup directory")
    return resolved_candidate


def _safe_name(label: str) -> str:
    """Normalize a user label for use in a backup filename."""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-.")
    return normalized[:80] or "project"


def write_backup(
    root: Path,
    project_id: int,
    payload: dict[str, Any],
    app_version: str,
    label: str = "project",
) -> tuple[str, BackupManifest]:
    """Atomically write a compressed, checksummed project backup."""
    if project_id < 1:
        raise BackupError("Project id must be positive")
    root.mkdir(parents=True, exist_ok=True)
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest = BackupManifest(
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
        app_version=app_version,
        sha256=hashlib.sha256(payload_bytes).hexdigest(),
    )
    envelope = BackupEnvelope(manifest=manifest, payload=payload)
    filename = f"{_safe_name(label)}-{project_id}-{manifest.created_at.strftime('%Y%m%dT%H%M%S%fZ')}.json.gz"
    target = _confined_path(root, root / filename)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        with gzip.open(temporary, "wb") as archive:
            archive.write(envelope.model_dump_json().encode())
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise BackupError("Unable to write backup archive") from exc
    return target.name, manifest


def read_backup(root: Path, filename: str) -> BackupEnvelope:
    """Read, validate, and checksum one confined backup archive."""
    if Path(filename).name != filename or not filename.endswith(".json.gz"):
        raise BackupError("Invalid backup filename")
    target = _confined_path(root, root / filename)
    try:
        with gzip.open(target, "rb") as archive:
            envelope = BackupEnvelope.model_validate_json(archive.read())
    except (OSError, ValueError) as exc:
        raise BackupError("Unable to read backup archive") from exc
    payload_bytes = json.dumps(
        envelope.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(payload_bytes).hexdigest() != envelope.manifest.sha256:
        raise BackupError("Backup checksum does not match its payload")
    return envelope
