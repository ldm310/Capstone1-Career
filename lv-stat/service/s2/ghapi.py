"""GitHub REST 읽기 부품. gh CLI 대신 쓴다. 표준 라이브러리(urllib)만 쓴다.

- 경로는 gh api처럼 앞의 '/'가 있어도 없어도 된다. 쿼리 값은 q()로 인코딩해 넣는다.
- 실패는 NotFound·RateLimited·GitHubError로만 낸다.
- 응답 헤더 이름은 소문자 키로 돌려준다.
- 토큰은 환경 변수 LV_GITHUB_TOKEN에서만 읽고, 어디에도 찍지 않는다.
- 시험용 환경 변수: LV_GITHUB_API(기본 https://api.github.com), LV_GITHUB_OFFLINE=1(모든 호출을 NotFound로).
"""
import http.client
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# 5xx·연결 오류 뒤 다시 시도하는 횟수(첫 시도 뒤 3번). 시험에서는 이 함수를 바꿔 기다림을 없앤다.
_sleep = time.sleep
RETRY_LIMIT = 3


class NotFound(Exception):
    """404·409·451: 없는 것으로 본다."""


class GitHubError(Exception):
    """그 밖의 실패. 5xx·연결 오류(본문을 받는 중 끊김 포함)는 3번 다시 한 뒤, 잘못된 주소·헤더는 바로 낸다."""


class RateLimited(Exception):
    """GitHub 호출 한도(429, 또는 403 + X-RateLimit-Remaining: 0)."""

    def __init__(self, reset_epoch):
        self.reset_epoch = reset_epoch
        minutes = max(1, math.ceil((reset_epoch - time.time()) / 60))
        super().__init__(f"GitHub 호출 한도에 걸렸습니다({minutes}분 뒤 다시 시도)")


def _base():
    return (os.environ.get("LV_GITHUB_API") or "https://api.github.com").rstrip("/")


def _url(path):
    """전체 URL은 그대로 쓴다. 경로는 앞의 '/'가 있어도 없어도 API 주소 뒤에 붙인다(gh api와 같음)."""
    if path.startswith(("http://", "https://")):
        return path
    return _base() + "/" + path.lstrip("/")


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme.lower(), parts.netloc.lower())


def _headers(url):
    """API 주소(LV_GITHUB_API 또는 기본값)와 같은 출처일 때만 토큰을 붙인다."""
    h = {"Accept": "application/vnd.github+json", "User-Agent": "lv-stat-worker"}
    token = os.environ.get("LV_GITHUB_TOKEN", "").strip()
    if token and _origin(url) == _origin(_base()):
        h["Authorization"] = f"Bearer {token}"
    return h


class _TokenSafeRedirect(urllib.request.HTTPRedirectHandler):
    """다른 출처로 넘어가는 3xx에서는 Authorization을 떼고 따라간다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _origin(newurl) != _origin(_base()):
            new.remove_header("Authorization")
        return new


def _reset_epoch(headers):
    try:
        return int(headers.get("x-ratelimit-reset"))
    except (TypeError, ValueError):
        return time.time() + 60


def request(path, timeout=30):
    """경로(gh api처럼 'repos/…'·'/repos/…' 둘 다 됨) 또는 전체 URL을 GET해 (본문 JSON, 소문자 헤더 dict)를 돌려준다."""
    if os.environ.get("LV_GITHUB_OFFLINE") == "1":
        raise NotFound("오프라인 시험 모드")
    url = _url(path)
    for attempt in range(RETRY_LIMIT + 1):
        opener = urllib.request.build_opener(_TokenSafeRedirect)
        try:
            req = urllib.request.Request(url, headers=_headers(url))
            with opener.open(req, timeout=timeout) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                raw = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            headers = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
            e.close()
            if status in (404, 409, 451):
                raise NotFound(f"HTTP {status}") from None
            if status == 429 or (status == 403 and headers.get("x-ratelimit-remaining") == "0"):
                raise RateLimited(_reset_epoch(headers)) from None
            if status >= 500:
                if attempt < RETRY_LIMIT:
                    _sleep(2 ** attempt)
                    continue
                raise GitHubError(f"HTTP {status}, {RETRY_LIMIT}번 다시 시도 뒤 실패") from None
            raise GitHubError(f"HTTP {status}") from None
        except http.client.InvalidURL:
            # 주소가 잘못됨(공백·제어 문자, 숫자가 아닌 포트). 다시 해도 같으므로 바로 실패.
            raise GitHubError("요청 주소가 잘못됐습니다") from None
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            # 연결 오류: 연결 실패·시간 초과, 본문을 받는 중 끊김(IncompleteRead), 깨진 응답(BadStatusLine 등).
            if attempt < RETRY_LIMIT:
                _sleep(2 ** attempt)
                continue
            raise GitHubError(f"연결 실패, {RETRY_LIMIT}번 다시 시도 뒤 실패") from None
        except ValueError as e:
            # 보내기 전 검사 실패(헤더 값, ASCII가 아닌 주소, scheme 없는 주소). 다시 해도 같다.
            # 원래 메시지에 토큰이 들어갈 수 있어 예외 종류만 남기고 원래 예외는 잇지 않는다.
            raise GitHubError(f"요청을 보내지 못했습니다({type(e).__name__})") from None
        try:
            body = json.loads(raw) if raw.strip() else None
        except ValueError:
            raise GitHubError("응답 JSON을 읽지 못했습니다") from None
        return body, headers
    raise GitHubError("요청 실패")  # 도달하지 않는다


def get(path, default=None):
    """단일 응답. 없으면(NotFound) default."""
    try:
        body, _ = request(path)
    except NotFound:
        return default
    return body


def _items(body):
    if body is None:
        return []
    if isinstance(body, dict) and "items" in body:
        return list(body["items"])
    if isinstance(body, list):
        return body
    return [body]


def _next_link(link_header):
    for m in re.finditer(r'<([^>]*)>([^<]*)', link_header or ""):
        if re.search(r'rel="?next"?\s*(;|,|$)', m.group(2)):
            return m.group(1)
    return None


def get_all(path, max_pages=10):
    """목록을 Link rel="next"를 따라 최대 max_pages쪽까지 모은다. 없으면 []."""
    items = []
    base_netloc = urllib.parse.urlsplit(_url("/")).netloc
    url = path
    for _ in range(max_pages):
        try:
            body, headers = request(url)
        except NotFound:
            break
        items.extend(_items(body))
        nxt = _next_link(headers.get("link"))
        if not nxt:
            break
        nxt = urllib.parse.urljoin(_url(url), nxt)
        # 토큰을 다른 호스트로 보내지 않도록 같은 호스트만 따라간다.
        if urllib.parse.urlsplit(nxt).netloc != base_netloc:
            break
        url = nxt
    return items


def q(s):
    """검색어·쿼리 값을 URL 인코딩한다."""
    return urllib.parse.quote(str(s), safe="")
