"""``xsource signals scan`` — emit xsource's forward Signals.

Builds xsource's forward-looking items and emits them to the shared fleet
Signal store (``signals/xsource/latest.jsonl``). Flag-gated on
``XSOURCE_EMIT_SIGNALS``; a no-op that prints ``disabled`` when off.

Verify locally before scheduling:
    uv run xsource signals scan                  # -> disabled (flag off)
    XSOURCE_EMIT_SIGNALS=1 uv run xsource signals scan  # -> emitted N
"""

from __future__ import annotations

import typer

from xsource.beat import write_heartbeat
from xsource.obs import run_session
from xsource.runtime import emit_heartbeat
from xsource.signals.emit import _enabled, scan_and_emit

_JOB_ID = "xsource.signals"

signals_app = typer.Typer(
    name="signals",
    help="Emit xsource forward items as fleet Signals (XSOURCE_EMIT_SIGNALS-gated).",
    no_args_is_help=True,
)


@signals_app.command("scan")
def cmd_scan() -> None:
    """Build and emit xsource's forward-item Signals. Prints ``emitted N``
    or ``disabled`` (flag off)."""
    with run_session(trigger="signals.scan", args={}):
        try:
            if not _enabled():
                emit_heartbeat(job_name="signals-scan", outcome="disabled", counts={"emitted": 0})
                write_heartbeat(_JOB_ID, ok=True, detail="disabled")
                typer.echo("signals: disabled (set XSOURCE_EMIT_SIGNALS=1 to enable)")
                return
            signals = scan_and_emit()
            emit_heartbeat(job_name="signals-scan", outcome="ok", counts={"emitted": len(signals)})
            write_heartbeat(_JOB_ID, ok=True, detail=f"emitted={len(signals)}")
            typer.echo(f"signals: emitted {len(signals)}")
        except Exception as exc:
            write_heartbeat(_JOB_ID, ok=False, detail=str(exc))
            raise
