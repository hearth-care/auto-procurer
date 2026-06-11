from typing import Any, Callable
from dataclasses import dataclass

@dataclass
class BlastRadius:
    summary: str
    reversible: str

@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    shelf: str
    title: str
    summary: str
    equivalent_cli: str
    run: Callable[[Any], None] | None = None
    blast_radius: BlastRadius | None = None
    beta: bool = False
    money_movement: bool = False

class WizardContext:
    state: dict[str, Any]
    client: Any
    console: Any
    input_fn: Callable[[str], str] | None
    confirm_fn: Callable[[str], bool] | None
    present: Any
    read_key: Any
    focus: str | None
    dry_run: bool
    authorize_apply: Any
    capability_key: str | None
    capability_money_movement: bool
    def __init__(self, **kwargs: Any) -> None: ...

def register_capability(spec: CapabilitySpec) -> Callable[[Any], Any]: ...
