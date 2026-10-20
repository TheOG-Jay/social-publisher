"""LinkedIn Posts API client (POST https://api.linkedin.com/rest/posts)."""
from __future__ import annotations

import logging
import re
import time

import requests

log = logging.getLogger(__name__)

API_URL = "https://api.linkedin.com/rest/posts"
MAX_LEN = 3000  # LinkedIn commentary limit

# LinkedIn's "little text" format reserves these characters; unescaped ones
# (notably parentheses) can truncate a post. '#' is left alone so hashtags work.
_RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~])")


class LinkedInError(Exception):
    """Non-retryable API failure."""


class TokenExpiredError(LinkedInError):
    """HTTP 401: token invalid or expired. Needs human action."""


def escape_commentary(text: str) -> str:
    return _RESERVED.sub(r"\\\1", text)


class LinkedInClient:
    def __init__(
        self,
        token: str,
        author: str,
        version: str,
        session: requests.Session | None = None,
        max_retries: int = 3,
        sleep=time.sleep,
    ):
        self._token = token
        self._author = author
        self._version = version
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "LinkedIn-Version": self._version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def build_payload(self, text: str) -> dict:
        return {
            "author": self._author,
            "commentary": escape_commentary(text),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

    def create_post(self, text: str) -> str:
        """Publish a text post and return its URN (from the x-restli-id header)."""
        if not text.strip():
            raise LinkedInError("Post text is empty")
        if len(text) > MAX_LEN:
            raise LinkedInError(f"Post is {len(text)} chars; LinkedIn allows {MAX_LEN}")

        payload = self.build_payload(text)
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._session.post(API_URL, headers=self._headers(), json=payload, timeout=30)
            except requests.RequestException as exc:
                if attempt == self._max_retries:
                    raise LinkedInError(f"Network error: {exc}") from exc
                self._backoff(attempt, f"network error ({exc})")
                continue

            if resp.status_code == 201:
                return resp.headers.get("x-restli-id", "")
            if resp.status_code == 401:
                raise TokenExpiredError("LinkedIn returned 401: token invalid or expired")
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self._max_retries:
                    raise LinkedInError(f"LinkedIn {resp.status_code} after {attempt} attempts")
                self._backoff(attempt, f"HTTP {resp.status_code}")
                continue
            raise LinkedInError(f"LinkedIn {resp.status_code}: {resp.text[:300]}")
        raise LinkedInError("Exhausted retries")  # pragma: no cover

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = 2 ** attempt
        log.warning("Retrying in %ss (attempt %s): %s", delay, attempt, reason)
        self._sleep(delay)
