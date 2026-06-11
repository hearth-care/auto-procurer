from collections.abc import Callable
from typing import Any

# Minimal stubs — tracks only the symbols xsource imports.
# Prefer upstream py.typed when the framework ships it.

class keys:
    @staticmethod
    def read_key() -> str: ...

class render:
    @staticmethod
    def render_note(label: str, detail: str) -> Any: ...

class shell:
    class Host:
        def __init__(self, **kwargs: Any) -> None: ...
        on_open: Callable[[], None]
        capture_state: Any
        build_walk_ctx: Any
        activate_pill: Any
        doctor_build_report: Any
        doctor_build_probes: Any
        doctor_fixes_for: Any
        doctor_unconfigured_renderable: Any
        usage: Any

    @staticmethod
    def _home(host: Any, screen: Any, read_key: Any) -> None: ...

class usage:
    pass

class obs:
    @staticmethod
    def make_obs(
        *, worker_id: str, runtime_env: str | None = None, reserved_prefix: str
    ) -> tuple[Callable[..., None], Any]: ...
