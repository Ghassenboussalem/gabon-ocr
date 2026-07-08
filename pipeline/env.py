"""Minimal .env loader (no external dependency).

Reads KEY=VALUE lines from a .env file at the project root and sets them in
os.environ *without* overwriting variables already present in the real
environment (so `set GEMINI_API_KEY=...` still wins over the file).

Supported syntax:
    KEY=value
    KEY="quoted value"      # surrounding single/double quotes are stripped
    # comments and blank lines are ignored
    export KEY=value        # a leading `export ` is tolerated
"""
from __future__ import annotations

import os
from pathlib import Path

# .env lives next to this package (project root = parent of pipeline/).
_DEFAULT_ENV = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or _DEFAULT_ENV
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        # Real environment variables take precedence over the file.
        os.environ.setdefault(key, val)
