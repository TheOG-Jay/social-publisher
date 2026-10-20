"""Command-line entry point. Exit code 0 = healthy, 1 = needs attention."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from publisher.ai import GeminiRewriter
from publisher.config import ConfigError, Settings
from publisher.linkedin import LinkedInClient
from publisher.pipeline import run_pipeline
from publisher.sheets import GoogleSheetClient

log = logging.getLogger("publisher")


def _setup_logging(level: str) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if os.getenv("LOG_FILE"):
        handlers.append(logging.FileHandler(os.environ["LOG_FILE"]))
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def run(dry_run: bool = False) -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 1

    if settings.token_expires_on:
        days_left = (settings.token_expires_on - datetime.now(settings.timezone).date()).days
        if days_left <= 7:
            log.warning("LinkedIn token expires in %d day(s) - renew it soon", days_left)

    rewriter = (
        GeminiRewriter(settings.gemini_api_key, settings.gemini_model)
        if settings.gemini_api_key
        else None
    )
    summary = run_pipeline(
        sheet=GoogleSheetClient(settings),
        linkedin=LinkedInClient(
            settings.linkedin_token, settings.linkedin_author, settings.linkedin_version
        ),
        tz=settings.timezone,
        rewriter=rewriter,
        dry_run=dry_run,
        max_posts=settings.max_posts_per_run,
    )
    log.info(
        "Done: posted=%d failed=%d would_post=%d skipped=%d",
        len(summary.posted), len(summary.failed), len(summary.would_post), summary.skipped,
    )
    return 1 if summary.token_expired else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish due posts from Google Sheets to LinkedIn")
    parser.add_argument("--dry-run", action="store_true", help="show what would post; change nothing")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
