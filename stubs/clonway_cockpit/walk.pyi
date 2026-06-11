from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

@dataclass
class Precondition:
    label: str
    ok: bool
    detail: str

@dataclass
class Step:
    label: str
    run: Callable[[Any, dict[str, Any]], StepResult]

@dataclass
class StepResult:
    ok: bool
    data: dict[str, Any] | None = None
    message: str = ""

def confirm_apply(ctx: Any, *, prompt: str = "", equivalent_cli: str) -> bool: ...
def make_walk_handler(
    *,
    title: str,
    steps: list[Step],
    blast_radius: Any,
    preconditions_fn: Callable[[Any], list[Precondition]],
    equivalent_cli: str,
    total: int | None = None,
) -> Callable[[Any], None]: ...
