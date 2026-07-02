"""Read-only staff directory sheet values."""

from __future__ import annotations

import json
import logging

from xsource.store.files import SyncedFile
from xsource.store.models import Supplier

log = logging.getLogger("xsource.book")

DIRECTORY_TITLE = "Supplier directory"

_HEAD = ["Name", "Categories", "Phone", "Email", "Preferred", "Last used", "Last price", "Notes"]


class DirectorySheetGone(RuntimeError):
    pass


def build_directory_values(suppliers: list[Supplier]) -> list[list[str]]:
    rows = [list(_HEAD)]
    for supplier in sorted(suppliers, key=lambda item: item.name.lower()):
        last_price = "—"
        if supplier.price_history:
            price = supplier.price_history[-1]
            last_price = f"£{price['amount']} ({price['job']})"
        last_note = supplier.notes[-1]["text"] if supplier.notes else "—"
        rows.append(
            [
                supplier.name,
                ", ".join(supplier.categories) or "—",
                supplier.phone or "—",
                supplier.email or "—",
                "yes" if supplier.preferred else "",
                supplier.last_used or "—",
                last_price,
                last_note,
            ]
        )
    return rows


def load_directory_state(state_file: SyncedFile) -> dict:
    state_file.hydrate()
    if not state_file.path.exists():
        return {}
    try:
        data = json.loads(state_file.path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_directory_state(state_file: SyncedFile, sheet_id: str, sheet_url: str) -> None:
    state_file.path.parent.mkdir(parents=True, exist_ok=True)
    state_file.path.write_text(json.dumps({"sheet_id": sheet_id, "sheet_url": sheet_url}) + "\n")
    state_file.upload()


def _create_directory_sheet(state_file, client, title, values, folder_id, share_with) -> dict:
    sheet_id, sheet_url = client.create_directory_sheet(title, values, folder_id, share_with)
    try:
        save_directory_state(state_file, sheet_id, sheet_url)
    except OSError as exc:
        log.warning("directory state save failed: %s", exc)
    return {
        "sheet_id": sheet_id,
        "sheet_url": sheet_url,
        "rows": len(values) - 1,
        "created": True,
    }


def publish_directory(
    suppliers: list[Supplier],
    *,
    state_file: SyncedFile,
    client,
    title: str,
    folder_id: str | None,
    share_with: str | None,
) -> dict:
    if not suppliers:
        raise ValueError("no suppliers to publish")
    values = build_directory_values(suppliers)
    state = load_directory_state(state_file)
    sheet_id = state.get("sheet_id")
    if sheet_id:
        try:
            client.update_directory_sheet(sheet_id, values)
        except DirectorySheetGone:
            return _create_directory_sheet(state_file, client, title, values, folder_id, share_with)
        return {
            "sheet_id": sheet_id,
            "sheet_url": state.get("sheet_url", ""),
            "rows": len(values) - 1,
            "created": False,
        }
    return _create_directory_sheet(state_file, client, title, values, folder_id, share_with)
