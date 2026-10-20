"""Google Sheets access layer (the 'CMS database')."""
from __future__ import annotations

import json
import logging
from typing import Protocol

from publisher.config import Settings
from publisher.models import HEADERS, TRUTHY, PostRow

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetClient(Protocol):
    def fetch_rows(self) -> list[PostRow]: ...

    def update_row(
        self,
        row_number: int,
        status: str,
        urn: str = "",
        error: str = "",
        published_text: str = "",
    ) -> None: ...


def parse_rows(values: list[list[str]]) -> list[PostRow]:
    """Convert raw sheet values (starting at row 2) into PostRow objects."""
    rows: list[PostRow] = []
    for offset, raw in enumerate(values):
        raw = list(raw) + [""] * (len(HEADERS) - len(raw))
        rows.append(
            PostRow(
                row_number=offset + 2,
                id=str(raw[0]).strip(),
                text=str(raw[1]).strip(),
                scheduled_raw=str(raw[2]).strip(),
                status=str(raw[3]).strip(),
                urn=str(raw[4]).strip(),
                ai_rewrite=str(raw[5]).strip().upper() in TRUTHY,
                error=str(raw[6]).strip(),
            )
        )
    return rows


class GoogleSheetClient:
    def __init__(self, settings: Settings):
        # Imported lazily so unit tests don't need the Google libraries.
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if settings.google_credentials_json:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(settings.google_credentials_json), scopes=SCOPES
            )
        else:
            creds = service_account.Credentials.from_service_account_file(
                settings.google_credentials_file, scopes=SCOPES
            )
        self._api = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
        self._id = settings.spreadsheet_id
        self._tab = f"'{settings.worksheet}'"

    def fetch_rows(self) -> list[PostRow]:
        result = (
            self._api.values()
            .get(spreadsheetId=self._id, range=f"{self._tab}!A2:H")
            .execute()
        )
        return parse_rows(result.get("values", []))

    def update_row(self, row_number, status, urn="", error="", published_text=""):
        r = row_number
        body = {
            "valueInputOption": "RAW",
            "data": [
                {"range": f"{self._tab}!D{r}:E{r}", "values": [[status, urn]]},
                {"range": f"{self._tab}!G{r}:H{r}", "values": [[error[:500], published_text]]},
            ],
        }
        self._api.values().batchUpdate(spreadsheetId=self._id, body=body).execute()
        log.debug("Row %s -> %s", r, status)
