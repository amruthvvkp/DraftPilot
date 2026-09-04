"""Test backup archive integrity and path confinement."""

from pathlib import Path

import pytest

from draftpilot.core.backup import BackupError, read_backup, write_backup
from draftpilot.api.backups import restore_backup_payload
from draftpilot.models import Project, StoryArtifact
from _async import run_async


class _RestoreSession:
    """Provide deterministic identifiers for isolated restore testing."""

    def __init__(self) -> None:
        """Initialize captured restored models."""
        self.added: list[object] = []
        self.next_id = 100

    def add(self, value: object) -> None:
        """Capture a model and assign its isolated identifier."""
        self.added.append(value)
        if isinstance(value, Project) and value.id is None:
            value.id = self.next_id
            self.next_id += 1
        if isinstance(value, StoryArtifact) and value.id is None:
            value.id = self.next_id
            self.next_id += 1

    async def flush(self) -> None:
        """Complete the fake flush operation."""

    async def commit(self) -> None:
        """Complete the fake commit operation."""


def test_backup_round_trip_and_checksum(tmp_path: Path) -> None:
    """Round-trip a project payload and preserve its manifest identity."""
    filename, manifest = write_backup(tmp_path, 12, {"title": "A story"}, "0.1.0", "A story")
    restored = read_backup(tmp_path, filename)
    assert restored.payload == {"title": "A story"}
    assert restored.manifest.project_id == 12
    assert restored.manifest.sha256 == manifest.sha256


def test_backup_rejects_traversal_and_tampering(tmp_path: Path) -> None:
    """Reject path traversal and modified archive contents."""
    filename, _ = write_backup(tmp_path, 4, {"title": "Safe"}, "0.1.0")
    with pytest.raises(BackupError):
        read_backup(tmp_path, f"../{filename}")
    archive = tmp_path / filename
    archive.write_bytes(archive.read_bytes()[:-1] + b"x")
    with pytest.raises(BackupError):
        read_backup(tmp_path, filename)


def test_backup_payload_can_carry_artifact_state_and_dependency_identity(tmp_path: Path) -> None:
    """Retain the fields needed to restore versioned artifact relationships."""
    payload = {
        "artifacts": [
            {"backup_id": 10, "kind": "brief", "title": "Brief", "content": "A story", "version": 4, "stale": False, "depends_on": [], "artifact_metadata": {}},
            {"backup_id": 11, "kind": "outline", "title": "Outline", "content": "A beat", "version": 7, "stale": True, "depends_on": [10], "artifact_metadata": {}},
        ]
    }
    filename, _ = write_backup(tmp_path, 12, payload, "0.1.0")
    assert read_backup(tmp_path, filename).payload == payload


def test_restore_preserves_artifact_versions_staleness_and_remapped_dependencies() -> None:
    """Restore artifact state while translating old IDs to the new project."""
    session = _RestoreSession()
    project = run_async(
        restore_backup_payload(
            session,  # type: ignore[arg-type]
            {
                "project": {"title": "Restored", "primary_language": "English", "languages": []},
                "artifacts": [
                    {"backup_id": 10, "kind": "brief", "title": "Brief", "content": "A story", "version": 4, "stale": False, "depends_on": [], "artifact_metadata": {}},
                    {"backup_id": 11, "kind": "outline", "title": "Outline", "content": "A beat", "version": 7, "stale": True, "depends_on": [10], "artifact_metadata": {}},
                ],
                "screenplays": [],
                "references": [],
            },
        )
    )
    restored = list({item.id: item for item in session.added if isinstance(item, StoryArtifact)}.values())
    assert project.id == 100
    assert [(item.version, item.stale, item.depends_on) for item in restored] == [(4, False, []), (7, True, [101])]
