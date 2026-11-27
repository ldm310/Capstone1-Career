"""ghapi.py 시험. 가짜 GitHub API를 127.0.0.1 빈 포트에 띄운다. 실제 GitHub는 부르지 않는다."""
import http.server
import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "s2"))

import ghapi  # noqa: E402

ENV_KEYS = ("LV_GITHUB_API", "LV_GITHUB_TOKEN", "LV_GITHUB_OFFLINE")


def resp(status=200, body=None, headers=None):
    import json

    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    return status, dict(headers or {}), raw


class FakeGitHub:
    """routes[path] = [응답, ...]. 두 개 이상이면 앞에서부터 하나씩 쓰고, 마지막은 계속 쓴다."""

    def __init__(self):
        self.routes = {}
        self.seen = []  # (path, Authorization 헤더 또는 None)
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.seen.append((self.path, self.headers.get("Authorization")))
                queue = owner.routes.get(self.path)
                if not queue:
                    status, headers, body = resp(404, {"message": "Not Found"})
                else:
                    status, headers, body = queue[0] if len(queue) == 1 else queue.pop(0)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class GhApiTest(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.addCleanup(self._restore_env)

        self.fake = FakeGitHub()
        self.addCleanup(self.fake.close)
        os.environ["LV_GITHUB_API"] = self.fake.base

        self.sleeps = []
        saved_sleep = ghapi._sleep
        ghapi._sleep = self.sleeps.append
        self.addCleanup(setattr, ghapi, "_sleep", saved_sleep)

    def _restore_env(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_get_all_follows_next_link(self):
        base = self.fake.base
        self.fake.routes["/repos/a/b/commits?page=1"] = [
            resp(200, [{"n": 1}], {"Link": '<%s/repos/a/b/commits?page=2>; rel="next"' % base})
        ]
        self.fake.routes["/repos/a/b/commits?page=2"] = [resp(200, [{"n": 2}])]
        self.assertEqual(
            ghapi.get_all("/repos/a/b/commits?page=1"), [{"n": 1}, {"n": 2}]
        )

    def test_search_items_unwrapped(self):
        self.fake.routes["/search/commits?q=x"] = [
            resp(200, {"items": [{"sha": "a"}, {"sha": "b"}]})
        ]
        self.assertEqual(
            ghapi.get_all("/search/commits?q=x"), [{"sha": "a"}, {"sha": "b"}]
        )

    def test_not_found_returns_default(self):
        self.assertIsNone(ghapi.get("/missing"))
        self.assertEqual(ghapi.get_all("/missing"), [])

    def test_rate_limit_raises_with_wait(self):
        reset = int(time.time()) + 120
        self.fake.routes["/limited"] = [
            resp(403, {"message": "rate limit"},
                 {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)})
        ]
        with self.assertRaises(ghapi.RateLimited) as cm:
            ghapi.get_all("/limited")
        message = str(cm.exception)
        self.assertTrue("2분" in message or "3분" in message, message)
        self.assertEqual(self.sleeps, [])  # 한도 응답은 다시 부르지 않는다

    def test_429_is_rate_limited(self):
        self.fake.routes["/slow"] = [
            resp(429, {"message": "slow down"},
                 {"X-RateLimit-Reset": str(int(time.time()) + 60)})
        ]
        with self.assertRaises(ghapi.RateLimited):
            ghapi.get("/slow")

    def test_token_header_only_when_set(self):
        self.fake.routes["/me"] = [resp(200, {})]
        os.environ["LV_GITHUB_TOKEN"] = "abc"
        ghapi.get("/me")
        self.assertEqual(self.fake.seen[-1][1], "Bearer abc")
        del os.environ["LV_GITHUB_TOKEN"]
        ghapi.get("/me")
        self.assertIsNone(self.fake.seen[-1][1])

    def test_offline_switch(self):
        self.fake.routes["/x"] = [resp(200, [{"n": 1}])]
        os.environ["LV_GITHUB_OFFLINE"] = "1"
        self.assertEqual(ghapi.get_all("/x"), [])
        self.assertEqual(self.fake.seen, [])

    def test_5xx_retries_then_succeeds(self):
        self.fake.routes["/flaky"] = [
            resp(503, {}), resp(502, {}), resp(200, {"ok": True})
        ]
        self.assertEqual(ghapi.get("/flaky"), {"ok": True})
        self.assertEqual(len(self.fake.seen), 3)
        self.assertEqual(len(self.sleeps), 2)

    def test_5xx_gives_up_after_three_retries(self):
        self.fake.routes["/down"] = [resp(500, {})]
        with self.assertRaises(ghapi.GitHubError):
            ghapi.get("/down")
        self.assertEqual(len(self.fake.seen), 4)  # 첫 시도 + 재시도 3번
        self.assertEqual(len(self.sleeps), 3)

    def test_connection_error_gives_up(self):
        os.environ["LV_GITHUB_API"] = "http://127.0.0.1:1"  # 닫힌 포트
        with self.assertRaises(ghapi.GitHubError):
            ghapi.get("/anything")
        self.assertEqual(len(self.sleeps), 3)

    def test_q_encodes_query(self):
        self.assertEqual(ghapi.q("a b&c"), "a%20b%26c")


if __name__ == "__main__":
    unittest.main()
