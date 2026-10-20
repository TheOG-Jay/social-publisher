"""Core orchestration: find due posts, publish them, record the outcome."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from publisher.ai import RewriteError
from publisher.linkedin import LinkedInError, TokenExpiredError
from publisher.models import FAILED, PENDING, POSTED, POSTING, PostRow

log = logging.getLogger(__name__)

_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d")


@dataclass
class RunSummary:
    posted: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    would_post: list[int] = field(default_factory=list)  # dry-run only
    skipped: int = 0
    token_expired: bool = False


def parse_schedule(raw: str, tz: tzinfo) -> datetime:
    for fmt in _FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date '{raw}' (expected YYYY-MM-DD HH:MM)")


def run_pipeline(
    sheet,
    linkedin,
    tz: tzinfo,
    rewriter=None,
    now: datetime | None = None,
    dry_run: bool = False,
    max_posts: int = 5,
) -> RunSummary:
    now = now or datetime.now(tz)
    summary = RunSummary()
    due: list[tuple[datetime, PostRow]] = []

    for row in sheet.fetch_rows():
        if row.status.strip().lower() != PENDING.lower():
            summary.skipped += 1
            continue
        try:
            when = parse_schedule(row.scheduled_raw, tz)
        except ValueError as exc:
            log.error("Row %s: %s", row.row_number, exc)
            if not dry_run:
                sheet.update_row(row.row_number, FAILED, error=str(exc))
            summary.failed.append(row.row_number)
            continue
        if when <= now:
            due.append((when, row))
        else:
            summary.skipped += 1

    due.sort(key=lambda pair: pair[0])  # oldest first
    log.info("%d post(s) due, %d skipped", len(due), summary.skipped)

    for _, row in due[:max_posts]:
        text = row.text
        if row.ai_rewrite and rewriter is not None:
            try:
                text = rewriter.rewrite(row.text)
            except RewriteError as exc:
                log.warning("Row %s: %s - using original text", row.row_number, exc)

        if dry_run:
            log.info("[dry-run] Row %s would post: %r", row.row_number, text[:80])
            summary.would_post.append(row.row_number)
            continue

        # Claim the row first so an overlapping run cannot publish it twice.
        sheet.update_row(row.row_number, POSTING)
        try:
            urn = linkedin.create_post(text)
        except TokenExpiredError as exc:
            log.critical("%s. Renew the token; remaining posts stay Pending.", exc)
            sheet.update_row(row.row_number, PENDING, error=str(exc))
            summary.token_expired = True
            break
        except LinkedInError as exc:
            log.error("Row %s failed: %s", row.row_number, exc)
            sheet.update_row(row.row_number, FAILED, error=str(exc))
            summary.failed.append(row.row_number)
            continue
        except Exception as exc:  # never lose track of a claimed row
            log.exception("Row %s unexpected error", row.row_number)
            sheet.update_row(row.row_number, FAILED, error=f"Unexpected: {exc}")
            summary.failed.append(row.row_number)
            continue

        sheet.update_row(row.row_number, POSTED, urn=urn, published_text=text)
        log.info("Row %s posted as %s", row.row_number, urn)
        summary.posted.append(row.row_number)

    return summary
