"""Optional Gemini-powered rewriting of raw notes into LinkedIn-ready posts."""
from __future__ import annotations

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = (
    "Rewrite the following raw notes as an engaging, professional LinkedIn post. "
    "Keep the original meaning, do not invent facts or numbers, use short paragraphs, "
    "at most 3 relevant hashtags, and stay under 1300 characters. "
    "Return only the post text.\n\nNOTES:\n{text}"
)


class RewriteError(Exception):
    pass


class GeminiRewriter:
    def __init__(self, api_key: str, model: str, session: requests.Session | None = None):
        self._key = api_key
        self._model = model
        self._session = session or requests.Session()

    def rewrite(self, text: str) -> str:
        try:
            resp = self._session.post(
                URL.format(model=self._model),
                headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": PROMPT.format(text=text)}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            out = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            raise RewriteError(f"Gemini rewrite failed: {exc}") from exc
        if not out:
            raise RewriteError("Gemini returned empty text")
        return out
