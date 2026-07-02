"""xsource's Typer CLI entry point.

``xsource`` (bare, on a TTY) opens the interactive cockpit; otherwise it
prints help so pipes / scheduled jobs keep working. Sub-apps:

* ``xsource signals scan`` — emit forward Signals to the fleet store
  (flag-guarded on ``XSOURCE_EMIT_SIGNALS``).
* ``xsource watcher ...`` — poll Gmail for supplier replies.
* ``xsource request ...`` — sync, trigger, follow up, and reorder procurement requests.
* ``xsource invoice ...`` — capture, re-emit, write off, and sync invoice acknowledgements.
"""

from __future__ import annotations

import sys

import typer

from xsource.cli.book import book_app
from xsource.cli.cockpit import run_cockpit, serve_agent
from xsource.cli.invoice import invoice_app
from xsource.cli.request import request_app
from xsource.cli.signals import signals_app
from xsource.cli.watcher import watcher_app

app = typer.Typer(
    name="xsource",
    help="Auto-Procurer (xsource) — Clonway fleet worker.",
    no_args_is_help=False,  # bare invocation opens the cockpit (or prints help off-TTY)
)
app.add_typer(signals_app, name="signals")
app.add_typer(watcher_app, name="watcher")
app.add_typer(request_app, name="request")
app.add_typer(invoice_app, name="invoice")
app.add_typer(book_app, name="book")


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    agent_stdio: bool = typer.Option(
        False, "--agent-stdio", help="Serve the cockpit to an agent over JSON stdin/stdout."
    ),
    allow_apply: bool = typer.Option(
        False, "--allow-apply", help="With --agent-stdio: opt into the guarded-apply handshake."
    ),
) -> None:
    """Bare ``xsource``: open the cockpit on a real TTY; ``--agent-stdio`` serves the
    SAME cockpit to an agent over line-delimited JSON; else print help so pipes and scheduled
    jobs keep today's behaviour."""
    if agent_stdio:
        serve_agent(allow_apply=allow_apply)
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return
    if sys.stdin.isatty() and sys.stdout.isatty():
        run_cockpit()
    else:
        typer.echo(ctx.get_help())


def main() -> None:
    app()
