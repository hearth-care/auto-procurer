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
