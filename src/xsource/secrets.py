"""Secret lookup helpers."""

from __future__ import annotations

import os
from pathlib import Path


def secret_from_env(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    path = os.environ.get(f"{name}_FILE", "")
    if not path:
        return ""
    return Path(path).expanduser().read_text().strip()
