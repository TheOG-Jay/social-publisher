"""Configuration loaded from environment variables (or a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    worksheet: str
    linkedin_token: str
    linkedin_author: str
    linkedin_version: str
    timezone: ZoneInfo
    google_credentials_file: str
    google_credentials_json: str | None
    gemini_api_key: str | None
    gemini_model: str
    token_expires_on: date | None
    max_posts_per_run: int

    @classmethod
    def from_env(cls) -> "Settings":
        try:  # optional convenience for local development
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
        try:
            tz = ZoneInfo(tz_name)
        except Exception as exc:  # ZoneInfoNotFoundError subclasses KeyError
            raise ConfigError(f"Invalid TIMEZONE: {tz_name}") from exc

        expires_raw = os.getenv("LINKEDIN_TOKEN_EXPIRES_ON", "").strip()
        expires_on = None
        if expires_raw:
            try:
                expires_on = date.fromisoformat(expires_raw)
            except ValueError as exc:
                raise ConfigError("LINKEDIN_TOKEN_EXPIRES_ON must be YYYY-MM-DD") from exc

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip() or None
        creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        if not creds_json and not os.path.exists(creds_file):
            raise ConfigError(
                "Provide GOOGLE_CREDENTIALS_JSON or a credentials file "
                f"at GOOGLE_CREDENTIALS_FILE (looked for: {creds_file})"
            )

        return cls(
            spreadsheet_id=_required("SPREADSHEET_ID"),
            worksheet=os.getenv("WORKSHEET_NAME", "Sheet1"),
            linkedin_token=_required("LINKEDIN_ACCESS_TOKEN"),
            linkedin_author=_required("LINKEDIN_PERSON_URN"),
            linkedin_version=os.getenv("LINKEDIN_VERSION", "202607"),
            timezone=tz,
            google_credentials_file=creds_file,
            google_credentials_json=creds_json,
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip() or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            token_expires_on=expires_on,
            max_posts_per_run=int(os.getenv("MAX_POSTS_PER_RUN", "5")),
        )
