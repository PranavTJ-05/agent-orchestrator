from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import ServerSpec

DEFAULT_DIR = Path(os.getenv("STUDIO_DIR", ".studio"))


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def write_private(path: Path, text: str) -> None:
    """Atomic write with owner-only permissions (files can hold API keys and tokens)."""
    _private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ServerStore:
    """Persists the list of MCP servers as JSON in .studio/servers.json (owner-only)."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = _private_dir(directory or DEFAULT_DIR)
        self.path = self.directory / "servers.json"

    def load(self) -> list[ServerSpec]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        specs = []
        for item in raw.get("servers", []):
            try:
                specs.append(ServerSpec.model_validate(item))
            except ValueError:
                continue  # skip a corrupt entry instead of losing every server
        return specs

    def save(self, specs: list[ServerSpec]) -> None:
        payload = {"version": 1, "servers": [s.model_dump(mode="json") for s in specs]}
        write_private(self.path, json.dumps(payload, indent=2))
