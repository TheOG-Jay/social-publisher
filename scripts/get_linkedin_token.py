"""One-time helper: run LinkedIn's OAuth flow and print your access token + member URN.

Prereqs (LinkedIn Developer Portal):
  * App with 'Share on LinkedIn' and 'Sign In with LinkedIn using OpenID Connect' products
  * Authorized redirect URL:  http://localhost:8080/callback
  * Env vars: LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET

Usage:  python scripts/get_linkedin_token.py
"""
import os
import secrets
import sys
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

REDIRECT = "http://localhost:8080/callback"
SCOPE = "openid profile w_member_social"
result: dict = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        result.update({k: v[0] for k, v in q.items()})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Done. You can close this tab and return to the terminal.")

    def log_message(self, *args):
        pass


def main() -> int:
    cid = os.getenv("LINKEDIN_CLIENT_ID")
    secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not cid or not secret:
        print("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET first.")
        return 1

    state = secrets.token_urlsafe(16)
    url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
        {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
         "state": state, "scope": SCOPE}
    )
    print("Opening browser to authorize...\n", url)
    webbrowser.open(url)
    HTTPServer(("localhost", 8080), Handler).handle_request()

    if result.get("state") != state or "code" not in result:
        print("Authorization failed:", result)
        return 1

    tok = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={"grant_type": "authorization_code", "code": result["code"],
              "redirect_uri": REDIRECT, "client_id": cid, "client_secret": secret},
        timeout=30,
    )
    tok.raise_for_status()
    data = tok.json()
    access = data["access_token"]

    info = requests.get("https://api.linkedin.com/v2/userinfo",
                        headers={"Authorization": f"Bearer {access}"}, timeout=30)
    info.raise_for_status()
    expires = date.today() + timedelta(seconds=int(data.get("expires_in", 0)))

    print("\nAdd these to your .env / GitHub secrets:\n")
    print(f"LINKEDIN_ACCESS_TOKEN={access}")
    print(f"LINKEDIN_PERSON_URN=urn:li:person:{info.json()['sub']}")
    print(f"LINKEDIN_TOKEN_EXPIRES_ON={expires.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
