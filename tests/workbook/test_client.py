from __future__ import annotations

from xsource.workbook.client import WorkbookClient
from xsource.workbook.contract import (
    BLACK_BOOK_COLUMNS,
    ENERGY_JOB_COLUMNS,
    FIRM_STAGES,
    FIXED_TABS,
    JOB_COLUMNS,
)


class _Exec:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {}

    def execute(self):
        return self.payload


class _Values:
    def __init__(self, calls, get_payload):
        self.calls, self.get_payload = calls, get_payload

    def update(self, **kw):
        self.calls.append(("values.update", kw))
        return _Exec()

    def clear(self, **kw):
        self.calls.append(("values.clear", kw))
        return _Exec()

    def get(self, **kw):
        self.calls.append(("values.get", kw))
        return _Exec(self.get_payload)


class _Spreadsheets:
    def __init__(self):
        self.calls = []
        self.existing = {"Board": 0, "Black book": 1, "Log": 2}
        self.get_payload = {"values": [["a", "b"]]}

    def values(self):
        return _Values(self.calls, self.get_payload)

    def create(self, **kw):
        self.calls.append(("create", kw))
        return _Exec({"spreadsheetId": "wb1", "spreadsheetUrl": "https://example.test/wb1"})

    def get(self, **kw):
        self.calls.append(("get", kw))
        return _Exec(
            {
                "sheets": [
                    {"properties": {"title": t, "sheetId": g}} for t, g in self.existing.items()
                ]
            }
        )

    def batchUpdate(self, **kw):
        self.calls.append(("batchUpdate", kw))
        return _Exec({"replies": [{"addSheet": {"properties": {"sheetId": 77}}}]})


class _Sheets:
    def __init__(self):
        self.s = _Spreadsheets()

    def spreadsheets(self):
        return self.s


class _Files:
    def __init__(self, calls):
        self.calls = calls

    def update(self, **kw):
        self.calls.append(("drive.update", kw))
        return _Exec()


class _Drive:
    def __init__(self):
        self.calls = []

    def files(self):
        return _Files(self.calls)


def _client():
    sheets, drive = _Sheets(), _Drive()
    return WorkbookClient.from_services(sheets, drive), sheets.s, drive


def _requests(sheets):
    out = []
    for name, kw in sheets.calls:
        if name == "batchUpdate":
            out.extend(kw["body"]["requests"])
    return out


def _protected(reqs):
    return [r["addProtectedRange"]["protectedRange"] for r in reqs if "addProtectedRange" in r]


def _cols(rng):
    return rng["startColumnIndex"], rng["endColumnIndex"]


def test_create_sends_fixed_tabs_in_order_and_moves_to_folder():
    client, sheets, drive = _client()
    assert client.create("Gareth", "folder9") == ("wb1", "https://example.test/wb1")
    body = sheets.calls[0][1]["body"]
    assert body["properties"]["title"] == "Gareth"
    assert [s["properties"]["title"] for s in body["sheets"]] == list(FIXED_TABS)
    assert drive.calls[0][1]["addParents"] == "folder9"


def test_create_without_folder_skips_drive():
    client, _, drive = _client()
    client.create("Gareth", None)
    assert drive.calls == []


def test_tab_ids_maps_name_to_gid():
    client, _, _ = _client()
    assert client.tab_ids("wb1") == {"Board": 0, "Black book": 1, "Log": 2}


def test_ensure_tab_existing_adds_nothing():
    client, sheets, _ = _client()
    assert client.ensure_tab("wb1", "Board", index=0) == 0
    assert _requests(sheets) == []


def test_ensure_tab_missing_adds_at_index_and_returns_new_gid():
    client, sheets, _ = _client()
    assert client.ensure_tab("wb1", "EICR Nov 2026", index=3) == 77
    assert _requests(sheets) == [
        {"addSheet": {"properties": {"title": "EICR Nov 2026", "index": 3}}}
    ]


def test_write_tab_user_entered_then_clears_below():
    client, sheets, _ = _client()
    client.write_tab("wb1", "Job's tab", [["a"], ["b"], ["c"]])
    update = next(kw for n, kw in sheets.calls if n == "values.update")
    clear = next(kw for n, kw in sheets.calls if n == "values.clear")
    assert update["valueInputOption"] == "USER_ENTERED"
    assert update["range"] == "'Job''s tab'!A1"
    assert clear["range"] == "'Job''s tab'!A4:Z"


def test_read_tab_uses_formatted_values():
    client, sheets, _ = _client()
    assert client.read_tab("wb1", "Board") == [["a", "b"]]
    get = next(kw for n, kw in sheets.calls if n == "values.get")
    assert get["valueRenderOption"] == "FORMATTED_VALUE"


def test_read_tab_empty_tab_gives_no_rows():
    client, sheets, _ = _client()
    sheets.get_payload = {}
    assert client.read_tab("wb1", "Log") == []


def test_every_format_freezes_and_bolds_header():
    for kind in ("board", "job", "energy", "black_book", "log"):
        client, sheets, _ = _client()
        client.format_tab("wb1", 5, kind)
        reqs = _requests(sheets)
        frozen = [r for r in reqs if "updateSheetProperties" in r]
        assert frozen[0]["updateSheetProperties"]["properties"]["gridProperties"] == {
            "frozenRowCount": 1
        }
        bold = [
            r
            for r in reqs
            if "repeatCell" in r and r["repeatCell"]["range"].get("endRowIndex") == 1
        ]
        assert bold[0]["repeatCell"]["cell"]["userEnteredFormat"]["textFormat"]["bold"] is True


def test_black_book_conditional_format_and_protection():
    client, sheets, _ = _client()
    client.format_tab("wb1", 1, "black_book")
    reqs = _requests(sheets)
    rules = [r["addConditionalFormatRule"]["rule"] for r in reqs if "addConditionalFormatRule" in r]
    assert rules[0]["booleanRule"]["condition"]["values"] == [
        {"userEnteredValue": '=AND(J2<>"",J2-TODAY()<60)'}
    ]
    j = BLACK_BOOK_COLUMNS.index("Tell them by")
    assert j == 9
    assert [_cols(p["range"]) for p in _protected(reqs)] == [(j, j + 1)]
    assert all(p["warningOnly"] is True for p in _protected(reqs))


def test_black_book_last_price_is_currency():
    client, sheets, _ = _client()
    client.format_tab("wb1", 1, "black_book")
    g = BLACK_BOOK_COLUMNS.index("Last price")
    cells = [
        r["repeatCell"]
        for r in _requests(sheets)
        if "repeatCell" in r and r["repeatCell"]["range"].get("startRowIndex") == 1
    ]
    currency = [
        c for c in cells if c["cell"]["userEnteredFormat"]["numberFormat"]["type"] != "DATE"
    ]
    assert [
        (_cols(c["range"]), c["cell"]["userEnteredFormat"]["numberFormat"]) for c in currency
    ] == [((g, g + 1), {"type": "CURRENCY", "pattern": "£#,##0.00"})]


_UK_DATE = {"type": "DATE", "pattern": "dd/mm/yyyy"}


def _date_columns(reqs, gid):
    return sorted(
        _cols(r["repeatCell"]["range"])[0]
        for r in reqs
        if "repeatCell" in r
        and r["repeatCell"]["range"]["sheetId"] == gid
        and r["repeatCell"]["cell"]["userEnteredFormat"].get("numberFormat") == _UK_DATE
    )


def test_create_sets_uk_locale_and_london_time():
    client, sheets, _ = _client()
    client.create("Gareth", None)
    props = sheets.calls[0][1]["body"]["properties"]
    assert (props["locale"], props["timeZone"]) == ("en_GB", "Europe/London")


def test_black_book_dates_are_drawn_day_month_year():
    client, sheets, _ = _client()
    client.format_tab("wb1", 1, "black_book")
    assert _date_columns(_requests(sheets), 1) == [
        BLACK_BOOK_COLUMNS.index(h) for h in ("Last used", "Contract ends", "Tell them by")
    ]


def test_uk_settings_on_an_existing_workbook_add_no_protections_or_rules():
    client, sheets, _ = _client()
    client.apply_uk_settings("wb1")
    client.apply_uk_settings("wb1")
    reqs = _requests(sheets)
    props = [r["updateSpreadsheetProperties"] for r in reqs if "updateSpreadsheetProperties" in r]
    assert (
        props
        == [
            {
                "properties": {"locale": "en_GB", "timeZone": "Europe/London"},
                "fields": "locale,timeZone",
            }
        ]
        * 2
    )
    assert _date_columns(reqs, 1) == sorted([5, 7, 9] * 2)
    assert not [r for r in reqs if set(r) - {"updateSpreadsheetProperties", "repeatCell"}]


def test_job_tab_prices_stage_validation_and_firm_protection():
    client, sheets, _ = _client()
    client.format_tab("wb1", 5, "job")
    reqs = _requests(sheets)
    first, latest = JOB_COLUMNS.index("First price"), JOB_COLUMNS.index("Latest price")
    cur = [
        _cols(r["repeatCell"]["range"])
        for r in reqs
        if "repeatCell" in r
        and r["repeatCell"]["cell"]["userEnteredFormat"].get("numberFormat", {}).get("type")
        == "CURRENCY"
    ]
    assert cur == [(first, first + 1), (latest, latest + 1)]
    stage = JOB_COLUMNS.index("Stage")
    val = next(r["setDataValidation"] for r in reqs if "setDataValidation" in r)
    assert _cols(val["range"]) == (stage, stage + 1)
    assert [v["userEnteredValue"] for v in val["rule"]["condition"]["values"]] == list(FIRM_STAGES)
    firm = JOB_COLUMNS.index("Firm")
    prot = _protected(reqs)
    assert [_cols(p["range"]) for p in prot] == [(firm, firm + 1)]
    assert prot[0]["warningOnly"] is True
    assert prot[0]["range"]["sheetId"] == 5


def test_energy_tab_currency_on_yearly_cost_only_plain_on_rates():
    client, sheets, _ = _client()
    client.format_tab("wb1", 5, "energy")
    reqs = _requests(sheets)
    fmts = {
        _cols(r["repeatCell"]["range"]): r["repeatCell"]["cell"]["userEnteredFormat"][
            "numberFormat"
        ]["type"]
        for r in reqs
        if "repeatCell" in r and "numberFormat" in r["repeatCell"]["cell"]["userEnteredFormat"]
    }
    unit = ENERGY_JOB_COLUMNS.index("Unit rate")
    standing = ENERGY_JOB_COLUMNS.index("Standing charge")
    yearly = ENERGY_JOB_COLUMNS.index("Est. yearly cost")
    assert fmts == {
        (unit, unit + 1): "NUMBER",
        (standing, standing + 1): "NUMBER",
        (yearly, yearly + 1): "CURRENCY",
    }


def test_board_protects_every_column_in_three_ranges():
    client, sheets, _ = _client()
    client.format_tab("wb1", 0, "board")
    prot = _protected(_requests(sheets))
    assert [_cols(p["range"]) for p in prot] == [(0, 3), (3, 7), (7, 9)]
    assert all(p["warningOnly"] for p in prot)


def test_log_is_fully_protected():
    client, sheets, _ = _client()
    client.format_tab("wb1", 2, "log")
    prot = _protected(_requests(sheets))
    assert [_cols(p["range"]) for p in prot] == [(0, 3)]
    assert prot[0]["warningOnly"] is True


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def execute(self):
        raise self.exc


def _http_error(status, reason):
    from googleapiclient.errors import HttpError

    return HttpError(type("Resp", (), {"status": status, "reason": reason})(), reason.encode())


def test_read_tab_signals_a_missing_tab_and_lets_other_errors_through():
    import pytest

    from xsource.workbook.client import TabMissing

    c, sheets, _ = _client()
    sheets.values = lambda: type(
        "V", (), {"get": lambda self, **kw: _Raises(_http_error(400, "Unable to parse range: X"))}
    )()
    with pytest.raises(TabMissing):
        c.read_tab("wb1", "X")
    sheets.values = lambda: type(
        "V", (), {"get": lambda self, **kw: _Raises(_http_error(404, "gone"))}
    )()
    with pytest.raises(TabMissing):
        c.read_tab("wb1", "X")
    sheets.values = lambda: type(
        "V", (), {"get": lambda self, **kw: _Raises(_http_error(500, "boom"))}
    )()
    from googleapiclient.errors import HttpError

    with pytest.raises(HttpError):
        c.read_tab("wb1", "X")
