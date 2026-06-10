"""Thin Sheets/Drive wrapper."""

from __future__ import annotations

from xsource.sheet.template import COLUMNS, STATUS_VALUES


class SheetClient:
    def __init__(self, creds):
        from googleapiclient.discovery import build

        self.sheets = build("sheets", "v4", credentials=creds)
        self.drive = build("drive", "v3", credentials=creds)

    def create_request_sheet(
        self,
        title: str,
        values: list[list[str]],
        folder_id: str | None,
        share_with: str | None,
    ) -> tuple[str, str]:
        body = {"properties": {"title": title}}
        ss = self.sheets.spreadsheets().create(body=body).execute()
        sid, url = ss["spreadsheetId"], ss["spreadsheetUrl"]
        self.sheets.spreadsheets().values().update(
            spreadsheetId=sid,
            range="A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
        status_col = COLUMNS.index("Status")
        self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid,
            body={
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": 0,
                                "startRowIndex": 1,
                                "endRowIndex": len(values) - 1,
                                "startColumnIndex": status_col,
                                "endColumnIndex": status_col + 1,
                            },
                            "rule": {
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": [
                                        {"userEnteredValue": value} for value in STATUS_VALUES
                                    ],
                                },
                                "strict": True,
                                "showCustomUi": True,
                            },
                        }
                    }
                ]
            },
        ).execute()
        if folder_id:
            self.drive.files().update(fileId=sid, addParents=folder_id, fields="id").execute()
        if share_with:
            self.drive.permissions().create(
                fileId=sid,
                body={"type": "group", "role": "writer", "emailAddress": share_with},
                sendNotificationEmail=False,
            ).execute()
        return sid, url

    def mark_asked(self, sheet_id: str, *, rank: int, asked_at, updated_at) -> None:
        row = rank + 1
        self.sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": [
                    {
                        "range": f"H{row}:M{row}",
                        "values": [
                            [
                                "Asked",
                                asked_at.strftime("%Y-%m-%d %H:%M"),
                                "",
                                "",
                                "",
                                updated_at.strftime("%Y-%m-%d %H:%M"),
                            ]
                        ],
                    }
                ],
            },
        ).execute()

    def write_reply(self, sheet_id: str, *, rank: int, parsed, received_at, updated_at) -> None:
        row = rank + 1
        status = {"quoted": "Quoted", "replied": "Replied", "no": "No"}.get(
            parsed.status, parsed.status.title()
        )
        self.sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": [
                    {
                        "range": f"H{row}:M{row}",
                        "values": [
                            [
                                status,
                                received_at.strftime("%Y-%m-%d %H:%M"),
                                parsed.summary,
                                "" if parsed.quote_amount is None else str(parsed.quote_amount),
                                "",
                                updated_at.strftime("%Y-%m-%d %H:%M"),
                            ]
                        ],
                    }
                ],
            },
        ).execute()

    def update_heartbeat(self, sheet_id: str, checked_at) -> None:
        self.sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="USER_ENTERED",
            body={"values": [[f"xsource last checked {checked_at.strftime('%Y-%m-%d %H:%M')}"]]},
        ).execute()

    def read_request_rows(self, sheet_id: str) -> list[dict[str, str | int]]:
        values = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="A:N")
            .execute()
            .get("values", [])
        )
        if not values:
            return []
        header = values[0]
        index = {name: idx for idx, name in enumerate(header)}
        rows = []
        for raw in values[1:]:
            if not raw or not str(raw[0]).isdigit():
                continue
            rows.append(
                {
                    "rank": int(raw[index["#"]]),
                    "status": raw[index["Status"]] if len(raw) > index["Status"] else "",
                    "quote": raw[index["Quote £"]] if len(raw) > index["Quote £"] else "",
                    "chosen": raw[index["Chosen"]] if len(raw) > index["Chosen"] else "",
                    "notes": raw[index["Notes"]] if len(raw) > index["Notes"] else "",
                }
            )
        return rows
