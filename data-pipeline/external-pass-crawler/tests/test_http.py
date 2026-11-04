import io
import unittest
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError
from external_pass_crawler.platforms.linkareer import PublicHttp, _NoRedirect
from external_pass_crawler.errors import AccessRestricted


class Response(io.BytesIO):
    status = 200
    def __init__(self, url, body):
        super().__init__(body.encode())
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain" if url.endswith("robots.txt") else "text/html"
    def geturl(self):
        return self.url


class HttpTests(unittest.TestCase):
    def test_robots_is_fetched_once_and_requests_are_spaced_with_timeout(self):
        opener, sleep = Mock(), Mock()
        opener.open.side_effect = [
            Response("https://linkareer.com/robots.txt", "User-agent: *\nAllow: /\n"),
            Response("https://linkareer.com/cover-letter/1", "<html>ok</html>"),
            Response("https://linkareer.com/cover-letter/2", "<html>ok</html>")]
        http = PublicHttp(2, 7, opener, clock=lambda: 0, sleep=sleep)
        http.get("/cover-letter/1"); http.get("/cover-letter/2")
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(c.kwargs["timeout"] == 7 for c in opener.open.call_args_list))

    def test_robots_denial_does_not_fetch_detail(self):
        opener = Mock()
        opener.open.return_value = Response("https://linkareer.com/robots.txt", "User-agent: *\nDisallow: /cover-letter/\n")
        with self.assertRaises(AccessRestricted):
            PublicHttp(opener=opener).get("/cover-letter/1")
        self.assertEqual(opener.open.call_count, 1)

    def test_http_restrictions_and_challenge_stop_without_retry(self):
        for status in (401, 403, 429):
            opener = Mock()
            opener.open.side_effect = [Response("https://linkareer.com/robots.txt", "User-agent: *\nAllow: /\n"),
                                      HTTPError("x", status, "blocked", {}, None)]
            with self.assertRaises(AccessRestricted):
                PublicHttp(opener=opener, sleep=lambda x: None).get("/cover-letter/1")
            self.assertEqual(opener.open.call_count, 2)
        with self.assertRaises(AccessRestricted):
            _NoRedirect().redirect_request(None, None, 302, "", {}, "https://linkareer.com/login")

    def test_invalid_route_cannot_fetch_arbitrary_url(self):
        opener = Mock()
        with self.assertRaises(AccessRestricted):
            PublicHttp(opener=opener).get("//attacker.invalid/")
        opener.open.assert_not_called()
