from __future__ import annotations

from xsource.workbook.client import TabMissing


class FakeStore:
    def __init__(self, records=()):
        self.records = {r.id: r for r in records}
        self.upserted = []

    def all(self):
        return list(self.records.values())

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, rec):
        self.records[rec.id] = rec
        self.upserted.append(rec)

    def next_id(self, prefix):
        return f"{prefix}-{len(self.records) + 1:04d}"


class FakeWorkbookClient:
    def __init__(self, tabs=None, ids=None, missing=()):
        self.missing = set(missing)
        self.tabs = dict(tabs or {})
        self.ids = dict(ids or {"Board": 0, "Black book": 1, "Log": 2})
        self.calls: list[tuple[str, str]] = []
        self.written: dict[str, list[list[str]]] = {}
        self.formatted: list[tuple[int, str]] = []

    def read_tab(self, wb, name):
        self.calls.append(("read_tab", name))
        if name in self.missing:
            raise TabMissing(name)
        # A real sheet shows what was last drawn until somebody edits it.
        return self.tabs.get(name, self.written.get(name, []))

    def write_tab(self, wb, name, rows):
        self.calls.append(("write_tab", name))
        self.written[name] = rows

    def tab_ids(self, wb):
        return dict(self.ids)

    def ensure_tab(self, wb, name, *, index):
        self.calls.append(("ensure_tab", name))
        self.ids[name] = max(self.ids.values()) + 1
        return self.ids[name]

    def format_tab(self, wb, gid, kind):
        self.formatted.append((gid, kind))
