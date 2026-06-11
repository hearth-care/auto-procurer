from typing import Any, Callable
from dataclasses import dataclass

@dataclass(frozen=True)
class Fix:
    title: str
    cmd: str
    note: str = ""
    run: Callable[[], str] | None = None
    confirm: bool = False

@dataclass(frozen=True)
class Probe:
    name: str
    level: str
    detail: str
    fix: Fix | None

def fixes_for(probes: list[Probe]) -> list[Fix]: ...
