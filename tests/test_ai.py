import unittest

import requests

from publisher.ai import GeminiRewriter, RewriteError


class Resp:
    def __init__(self, payload=None, error=None):
        self._p, self._e = payload, error

    def raise_for_status(self):
        if self._e:
            raise self._e

    def json(self):
        return self._p


class Session:
    def __init__(self, resp):
        self.resp, self.last = resp, None

    def post(self, url, **kw):
        self.last = (url, kw)
        return self.resp


class AITests(unittest.TestCase):
    def test_returns_generated_text(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "  Polished post  "}]}}]}
        s = Session(Resp(payload))
        out = GeminiRewriter("key", "model-x", session=s).rewrite("raw")
        self.assertEqual(out, "Polished post")
        self.assertIn("model-x", s.last[0])
        self.assertEqual(s.last[1]["headers"]["x-goog-api-key"], "key")

    def test_http_error_wrapped(self):
        s = Session(Resp(error=requests.HTTPError("500")))
        with self.assertRaises(RewriteError):
            GeminiRewriter("k", "m", session=s).rewrite("raw")

    def test_malformed_response_wrapped(self):
        with self.assertRaises(RewriteError):
            GeminiRewriter("k", "m", session=Session(Resp({"candidates": []}))).rewrite("raw")


if __name__ == "__main__":
    unittest.main()
