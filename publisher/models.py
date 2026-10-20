"""Shared data models and constants."""
from __future__ import annotations

from dataclasses import dataclass

# Sheet status values (column D)
PENDING = "Pending"
POSTING = "Posting"  # claimed by a run; prevents duplicate posts
POSTED = "Posted"
FAILED = "Failed"

# Column layout (A..H). Keep in sync with sample_sheet.csv and the README.
HEADERS = [
    "ID",              # A
    "Post Text",       # B
    "Scheduled Time",  # C  e.g. 2026-10-25 09:00 (in TIMEZONE)
    "Status",          # D  Pending | Posting | Posted | Failed
    "Post URN",        # E  written by the pipeline
    "AI Rewrite",      # F  TRUE/FALSE
    "Error",           # G  written by the pipeline
    "Published Text",  # H  final text that went live
]

TRUTHY = {"TRUE", "YES", "Y", "1", "X", "\u2713"}


@dataclass
class PostRow:
    row_number: int          # 1-based row number in the sheet
    id: str
    text: str
    scheduled_raw: str
    status: str
    urn: str = ""
    ai_rewrite: bool = False
    error: str = ""
