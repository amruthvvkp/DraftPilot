"""Test durable, confined screenplay export artifacts."""

from pathlib import Path

import pytest

from draftpilot.core.exports import ExportError, write_export


def test_write_export_is_confined_and_checksumed(tmp_path: Path) -> None:
    """Write a safe export artifact with a reproducible checksum."""
    artifact = write_export(tmp_path, 4, 9, "A House / A Story", "fountain", b"INT. HOUSE", 100)
    target = tmp_path / "exports" / artifact.filename
    assert target.read_bytes() == b"INT. HOUSE"
    assert artifact.bytes == 10
    assert len(artifact.sha256) == 64


def test_write_export_rejects_oversized_content(tmp_path: Path) -> None:
    """Reject content beyond the artifact size bound."""
    with pytest.raises(ExportError):
        write_export(tmp_path, 4, 9, "Story", "pdf", b"too large", 3)
