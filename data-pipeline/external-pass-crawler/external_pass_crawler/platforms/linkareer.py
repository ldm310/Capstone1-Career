import time
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from ..errors import AccessRestricted, FetchError
from .linkareer_parser import parse_search, parse_detail

BASE = "https://linkareer.com"
AGENT = "CareerExternalPassCrawler/0.1"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A login/challenge/host redirect is never followed.
        raise AccessRestricted("Redirect requires manual review")


class PublicHttp:
    def __init__(self, interval=2.0, timeout=20.0, opener=None, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.timeout = interval, timeout
        self.opener = opener or build_opener(_NoRedirect())
        self.clock, self.sleep = clock, sleep
        self.last = None
        self.robot = None

    def _fetch(self, path):
        if not path.startswith("/") or path.startswith("//"):
            raise AccessRestricted()
        if self.last is not None:
            self.sleep(max(0, self.interval - (self.clock() - self.last)))
        self.last = self.clock()
        try:
            with self.opener.open(Request(BASE + path, headers={"User-Agent": AGENT, "Accept": "text/html,text/plain"}), timeout=self.timeout) as response:
                if response.status != 200 or response.geturl() != BASE + path:
                    raise AccessRestricted()
                content_type = response.headers.get_content_type()
                if content_type not in ("text/html", "text/plain"):
                    raise FetchError("Unexpected content type")
                body = response.read(4_000_001)
                if len(body) > 4_000_000:
                    raise FetchError("Response too large")
                text = body.decode("utf-8")
                if re.search(r"<title[^>]*>[^<]*(?:captcha|access denied|just a moment)", text, re.I) or re.search(r'<(?:form|iframe)[^>]*(?:captcha|challenge)', text, re.I):
                    raise AccessRestricted()
                return text
        except HTTPError as exc:
            exc.close()
            if exc.code in (401, 403, 429):
                raise AccessRestricted() from None
            raise FetchError() from None
        except (URLError, TimeoutError, OSError, UnicodeError):
            raise FetchError() from None

    def get(self, path):
        if not re.fullmatch(r"/cover-letter/(?:search(?:\?.*)?|\d+)", path):
            raise AccessRestricted()
        if self.robot is None:
            self.robot = RobotFileParser()
            self.robot.parse(self._fetch("/robots.txt").splitlines())
            delay = self.robot.crawl_delay(AGENT)
            if delay:
                self.interval = max(self.interval, delay)
        if not self.robot.can_fetch(AGENT, BASE + path):
            raise AccessRestricted("robots.txt disallows this path")
        return self._fetch(path)


class LinkareerAdapter:
    source_platform = "linkareer"

    def __init__(self, http):
        self.http = http

    def search(self, company, page):
        query = urlencode({"organizationName": company, "page": page, "sort": "RELEVANCE", "tab": "all"})
        return parse_search(self.http.get("/cover-letter/search?" + query))

    def detail(self, external_id):
        if not re.fullmatch(r"\d+", external_id):
            raise AccessRestricted()
        return parse_detail(self.http.get("/cover-letter/" + external_id), external_id)
