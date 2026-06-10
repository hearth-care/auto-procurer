"""S1 — write-gate / draft-never-send characterisation, inherited by construction.

Every xsource write capability runs through the framework's single write
gate (``clonway_cockpit.walk.confirm_apply``): the ONLY place a walk may commit a
change. The gate fails CLOSED — anything but the confirm keys cancels — so a
generated worker can't send/post without an explicit operator confirm. The
example capability is read-only (a stricter floor); this pins the gate contract
the worker inherits, so a future real write capability keeps the safety floor.
"""

from __future__ import annotations

from clonway_cockpit import keys, registry, walk
from clonway_cockpit.registry import WizardContext
from rich.console import Console

from xsource.cli import cockpit


def _ctx(*, read_key=None, confirm_fn=lambda _p: False) -> WizardContext:
    return WizardContext(
        state={},
        client=None,
        console=Console(),
        input_fn=lambda *a, **k: "",
        confirm_fn=confirm_fn,
        read_key=read_key,
    )


def test_write_gate_accepts_only_confirm_keys() -> None:
    # ENTER / a / A confirm; everything else (incl. a stray key) fails closed.
    for key in (keys.ENTER, "a", "A"):
        assert walk.confirm_apply(_ctx(read_key=lambda k=key: k), equivalent_cli="x") is True
    for key in (keys.ESC, "n", "N", "x", " "):
        assert walk.confirm_apply(_ctx(read_key=lambda k=key: k), equivalent_cli="x") is False


def test_request_new_declares_no_email_send_or_draft() -> None:
    cockpit.register_all()
    spec = next(s for s in registry.get_capabilities() if s.key == "request.new")
    assert spec.blast_radius is not None
    assert "does not send or draft" in spec.blast_radius.summary.lower()
