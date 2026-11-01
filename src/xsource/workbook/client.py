from __future__ import annotations

from typing import Any, Literal

from xsource.workbook.contract import (
    BLACK_BOOK_COLUMNS,
    BOARD_COLUMNS,
    ENERGY_JOB_COLUMNS,
    FIRM_STAGES,
    FIXED_TABS,
    JOB_COLUMNS,
    LOG_COLUMNS,
)

Kind = Literal["board", "job", "energy", "black_book", "log"]

_CURRENCY = {"type": "CURRENCY", "pattern": "£#,##0.00"}
_PLAIN_NUMBER = {"type": "NUMBER", "pattern": "0.00##"}
# Every tab is created with Sheets' default 26 columns, so Z is the full span.
_LAST_COLUMN = "Z"
_TELL_THEM_BY_RED = '=AND(J2<>"",J2-TODAY()<60)'


def _quoted(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _span(gid: int, headers: tuple[str, ...], first: str, last: str | None = None) -> dict:
    start = headers.index(first)
    end = headers.index(last or first) + 1
    return {
        "sheetId": gid,
        "startRowIndex": 1,
        "startColumnIndex": start,
        "endColumnIndex": end,
    }


class TabMissing(Exception):
    pass


class WorkbookClient:
    def __init__(self, creds):
        from googleapiclient.discovery import build

        self.sheets = build("sheets", "v4", credentials=creds)
        self.drive = build("drive", "v3", credentials=creds)

    @classmethod
    def from_services(cls, sheets, drive) -> WorkbookClient:
        client = cls.__new__(cls)
        client.sheets = sheets
        client.drive = drive
        return client

    def create(self, title: str, folder_id: str | None) -> tuple[str, str]:
        body = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": name, "index": i}} for i, name in enumerate(FIXED_TABS)
            ],
        }
        ss = self.sheets.spreadsheets().create(body=body).execute()
        sid, url = ss["spreadsheetId"], ss["spreadsheetUrl"]
        if folder_id:
            self.drive.files().update(fileId=sid, addParents=folder_id, fields="id").execute()
        return sid, url

    def tab_ids(self, workbook_id: str) -> dict[str, int]:
        ss = (
            self.sheets.spreadsheets()
            .get(spreadsheetId=workbook_id, fields="sheets.properties(sheetId,title)")
            .execute()
        )
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in ss.get("sheets", [])}

    def ensure_tab(self, workbook_id: str, name: str, *, index: int) -> int:
        existing = self.tab_ids(workbook_id)
        if name in existing:
            return existing[name]
        reply = (
            self.sheets.spreadsheets()
            .batchUpdate(
                spreadsheetId=workbook_id,
                body={"requests": [{"addSheet": {"properties": {"title": name, "index": index}}}]},
            )
            .execute()
        )
        return reply["replies"][0]["addSheet"]["properties"]["sheetId"]

    def write_tab(self, workbook_id: str, name: str, rows: list[list[str]]) -> None:
        self.sheets.spreadsheets().values().update(
            spreadsheetId=workbook_id,
            range=f"{_quoted(name)}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        self.sheets.spreadsheets().values().clear(
            spreadsheetId=workbook_id,
            range=f"{_quoted(name)}!A{len(rows) + 1}:{_LAST_COLUMN}",
            body={},
        ).execute()

    def read_tab(self, workbook_id: str, name: str) -> list[list[str]]:
        from googleapiclient.errors import HttpError

        try:
            got = (
                self.sheets.spreadsheets()
                .values()
                .get(
                    spreadsheetId=workbook_id,
                    range=_quoted(name),
                    valueRenderOption="FORMATTED_VALUE",
                )
                .execute()
            )
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status == 404 or (status == 400 and "Unable to parse range" in str(exc)):
                raise TabMissing(name) from exc
            raise
        return got.get("values", [])

    def format_tab(self, workbook_id: str, gid: int, kind: Kind) -> None:
        headers = {
            "board": BOARD_COLUMNS,
            "job": JOB_COLUMNS,
            "energy": ENERGY_JOB_COLUMNS,
            "black_book": BLACK_BOOK_COLUMNS,
            "log": LOG_COLUMNS,
        }[kind]
        requests: list[dict[str, Any]] = [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat.bold",
                }
            },
        ]

        def number_format(first: str, fmt: dict) -> None:
            requests.append(
                {
                    "repeatCell": {
                        "range": _span(gid, headers, first),
                        "cell": {"userEnteredFormat": {"numberFormat": fmt}},
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )

        protect_spans: list[tuple[str, str]] = []
        if kind == "board":
            protect_spans = [
                ("Job", "Stage"),
                ("Firms keen", "Best firm"),
                ("Next step", "Waiting on"),
            ]
        elif kind in ("job", "energy"):
            protect_spans = [("Firm", "Firm")]
            if kind == "job":
                number_format("First price", _CURRENCY)
                number_format("Latest price", _CURRENCY)
            else:
                number_format("Unit rate", _PLAIN_NUMBER)
                number_format("Standing charge", _PLAIN_NUMBER)
                number_format("Est. yearly cost", _CURRENCY)
            requests.append(
                {
                    "setDataValidation": {
                        "range": _span(gid, headers, "Stage"),
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": s} for s in FIRM_STAGES],
                            },
                            "strict": True,
                            "showCustomUi": True,
                        },
                    }
                }
            )
        elif kind == "black_book":
            protect_spans = [("Tell them by", "Tell them by")]
            number_format("Last price", _CURRENCY)
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [_span(gid, headers, "Tell them by")],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": _TELL_THEM_BY_RED}],
                                },
                                "format": {"textFormat": {"foregroundColor": {"red": 0.8}}},
                            },
                        },
                        "index": 0,
                    }
                }
            )
        else:
            protect_spans = [("When", "What happened")]

        for first, last in protect_spans:
            rng = _span(gid, headers, first, last)
            del rng["startRowIndex"]
            requests.append(
                {"addProtectedRange": {"protectedRange": {"range": rng, "warningOnly": True}}}
            )

        self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=workbook_id, body={"requests": requests}
        ).execute()
