import unittest

import requests

from publisher.linkedin import (
    LinkedInClient, LinkedInError, TokenExpiredError, escape_commentary,
)


class Resp:
    def __init__(self, status, headers=None, text=""):
        self.status_code, self.headers, self.text = status, headers or {}, text


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(session, retries=3):
    return LinkedInClient("tok", "urn:li:person:abc", "202607", session=session,
                          max_retries=retries, sleep=lambda s: None)


class LinkedInTests(unittest.TestCase):
    def test_success_returns_urn_and_sends_required_headers(self):
        s = FakeSession(Resp(201, {"x-restli-id": "urn:li:share:99"}))
        urn = client(s).create_post("Hello world")
        self.assertEqual(urn, "urn:li:share:99")
        call = s.calls[0]
        self.assertEqual(call["url"], "https://api.linkedin.com/rest/posts")
        self.assertEqual(call["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(call["headers"]["LinkedIn-Version"], "202607")
        self.assertEqual(call["headers"]["X-Restli-Protocol-Version"], "2.0.0")
        self.assertEqual(call["json"]["author"], "urn:li:person:abc")
        self.assertEqual(call["json"]["distribution"]["feedDistribution"], "MAIN_FEED")

    def test_401_raises_token_expired_without_retry(self):
        s = FakeSession(Resp(401))
        with self.assertRaises(TokenExpiredError):
            client(s).create_post("x")
        self.assertEqual(len(s.calls), 1)

    def test_retries_on_5xx_then_succeeds(self):
        s = FakeSession(Resp(503), Resp(429), Resp(201, {"x-restli-id": "u"}))
        self.assertEqual(client(s).create_post("x"), "u")
        self.assertEqual(len(s.calls), 3)

    def test_gives_up_after_max_retries(self):
        s = FakeSession(Resp(500), Resp(500))
        with self.assertRaises(LinkedInError):
            client(s, retries=2).create_post("x")
        self.assertEqual(len(s.calls), 2)

    def test_4xx_is_not_retried(self):
        s = FakeSession(Resp(422, text="bad payload"))
        with self.assertRaises(LinkedInError) as ctx:
            client(s).create_post("x")
        self.assertIn("422", str(ctx.exception))
        self.assertEqual(len(s.calls), 1)

    def test_network_error_is_retried(self):
        s = FakeSession(requests.ConnectionError("down"), Resp(201, {"x-restli-id": "u"}))
        self.assertEqual(client(s).create_post("x"), "u")

    def test_rejects_empty_and_oversized_text(self):
        c = client(FakeSession())
        with self.assertRaises(LinkedInError):
            c.create_post("   ")
        with self.assertRaises(LinkedInError):
            c.create_post("a" * 3001)

    def test_escape_reserved_characters_but_keep_hashtags(self):
        self.assertEqual(escape_commentary("Hi (team) #python a_b"), "Hi \\(team\\) #python a\\_b")


if __name__ == "__main__":
    unittest.main()
