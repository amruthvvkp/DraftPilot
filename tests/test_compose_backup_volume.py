"""Check every Compose service that writes backups or exports shares the backup volume (#52)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRITERS = ("ui", "mcp", "worker")
OVERLAYS = ((), ("compose.dev.yml",), ("compose.release.yml",))


def _config(overlays: tuple[str, ...]) -> dict:
    """Return the resolved Compose config for `compose.yml` plus the given overlays."""
    files = [arg for name in ("compose.yml", *overlays) for arg in ("-f", str(ROOT / name))]
    result = subprocess.run(
        ["docker", "compose", *files, "config", "--format", "json", "--no-interpolate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _environment(service: dict) -> dict[str, str]:
    """Return a service's environment as a mapping, whether Compose emitted a list or a dict."""
    environment = service.get("environment", {})
    if isinstance(environment, list):
        return dict(item.split("=", 1) for item in environment)
    return environment


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker compose is not installed")
@pytest.mark.parametrize("overlays", OVERLAYS, ids=lambda value: "+".join(value) or "base")
def test_backup_writers_mount_backup_volume(overlays: tuple[str, ...]) -> None:
    """Mount `backup_data` at `BACKUP__ROOT` on ui, mcp and worker in every stack variant."""
    services = _config(overlays)["services"]
    for name in WRITERS:
        service = services[name]
        root = _environment(service)["BACKUP__ROOT"]
        mounts = {(volume.get("source"), volume["target"]) for volume in service.get("volumes", [])}
        assert ("backup_data", root) in mounts, f"{name} does not mount backup_data at {root}"
