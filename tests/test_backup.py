"""Test backup archive integrity and path confinement."""

from pathlib import Path

import pytest

from draftpilot.core.backup import BackupError, read_backup, write_backup


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
