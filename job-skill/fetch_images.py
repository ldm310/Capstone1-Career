"""
1단계: 사람인 공고 본문(relay 페이지)에서 이미지를 받아 images/ 에 저장한다.

  - 본문 HTML 의 <img src> 를 문서 순서대로 모으고 사람인 템플릿 이미지는 뺀다.
  - 모든 요청(본문·이미지) 사이에 최소 MIN_GAP 초를 둔다(초당 1건 이하).
  - User-Agent 는 브라우저로 위장하지 않고 프로젝트 이름을 쓴다.
  - 열리지 않는 공고(HTTP 오류, 본문 없음)는 건너뛰고 images/skipped.tsv 에 사유를 남긴다.
  - 받은 본문은 pages/ 에 캐시해 재실행 시 다시 요청하지 않는다.

실행: py -3.12 fetch_images.py   (이미지 크기 기록에 Pillow 사용, 없으면 크기만 비워 둔다)
"""

from __future__ import annotations

import csv
import html
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

from common import IMG_DIR, MANIFEST, PAGE_DIR, load_targets

RELAY = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={id}&rec_seq=0"
UA = "job_skill_extractor-ocr_test/0.1"
# 사람인이 공고 양식에 넣는 기본 이미지(내용 아님). 회사가 올린 이미지는 www.saraminimage.co.kr/recruit/… 아래에 있다.
TEMPLATES = ("saraminimage.co.kr/sri/vix/template/",      # 양식 장식
             "static.saraminimage.co.kr/static/hiring/images/",  # 빈 칸(blank.png)·상단 장식(template/toptype/…)
             "/recruit/bbs_recruit/watermark_")           # 워터마크(Designed by saramin 등)
TEMPLATE = TEMPLATES[0]


def is_template(url: str) -> bool:
    return any(t in url for t in TEMPLATES)
MIN_GAP = 1.2  # 초. 초당 1건 이하를 지키려고 여유를 둔다.

EXT_BY_TYPE = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
               "image/gif": "gif", "image/webp": "webp", "image/bmp": "bmp"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()
# 회사 서버 등 외부 이미지 호스트의 인증서 체인이 불완전할 때만 쓰는 폴백(사람인에는 쓰지 않는다).
_SSL_LAX = ssl._create_unverified_context()

_last = [0.0]


def _throttle() -> None:
    gap = time.monotonic() - _last[0]
    if gap < MIN_GAP:
        time.sleep(MIN_GAP - gap)
    _last[0] = time.monotonic()


def _safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme,
        parts.netloc.encode("idna").decode("ascii"),
        urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;="),
        urllib.parse.quote(parts.query, safe="=&%+/:@!$'()*,;"),
        "",
    ))


def get(url: str, referer: str | None = None, lax_ok: bool = False):
    """(status, content_type, body bytes). 연결 실패면 status=None."""
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(_safe_url(url), headers=headers)
    for ctx in ((_SSL, _SSL_LAX) if lax_ok else (_SSL,)):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                return r.status, (r.headers.get("Content-Type") or "").split(";")[0].strip().lower(), r.read()
        except urllib.error.HTTPError as e:
            return e.code, "", b""
        except urllib.error.URLError as e:
            if ctx is _SSL and lax_ok and isinstance(getattr(e, "reason", None), ssl.SSLError):
                continue
            print(f"    [연결 실패] {url[:90]} -> {e}")
            return None, "", b""
        except Exception as e:
            print(f"    [연결 실패] {url[:90]} -> {type(e).__name__}: {e}")
            return None, "", b""
    return None, "", b""


_IMG = re.compile(r"<img\b[^>]*>", re.I)
_ATTR = re.compile(r"""\b(src|data-src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)


def image_urls(page_html: str, base: str) -> list[str]:
    urls = []
    for tag in _IMG.findall(page_html):
        attrs = {m.group(1).lower(): (m.group(2) or m.group(3) or m.group(4) or "") for m in _ATTR.finditer(tag)}
        src = attrs.get("src") or attrs.get("data-src") or ""
        src = html.unescape(src).strip()
        if not src or src.startswith("data:"):
            continue
        src = urllib.parse.urljoin(base, src)
        if is_template(src) or src in urls:
            continue
        urls.append(src)
    return urls


def image_size(path: str) -> tuple[str, str]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return str(im.width), str(im.height)
    except Exception:
        return "", ""


def main() -> None:
    os.makedirs(PAGE_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    manifest, skipped = [], []

    for t in load_targets():
        rid = t["rec_idx"]
        url = RELAY.format(id=rid)
        page_path = os.path.join(PAGE_DIR, f"{rid}.html")
        print(f"[{rid}] {t['company']} | {t['title']}")

        if os.path.exists(page_path):
            with open(page_path, encoding="utf-8") as f:
                page = f.read()
            status = 200
        else:
            status, _, body = get(url)
            page = body.decode("utf-8", "replace")
            if status == 200 and page:
                with open(page_path, "w", encoding="utf-8") as f:
                    f.write(page)

        if status != 200 or "user_content" not in page:
            reason = f"HTTP {status}" if status != 200 else "본문(user_content) 없음"
            print(f"    건너뜀: {reason}")
            skipped.append({"rec_idx": rid, "reason": reason})
            continue

        urls = image_urls(page, url)
        if not urls:
            print("    건너뜀: 본문 이미지 없음")
            skipped.append({"rec_idx": rid, "reason": "본문 이미지 없음"})
            continue

        for seq, img_url in enumerate(urls, 1):
            status, ctype, data = get(img_url, referer=url, lax_ok=True)
            row = {"rec_idx": rid, "seq": seq, "url": img_url, "file": "", "bytes": len(data),
                   "width": "", "height": "", "status": status}
            if status == 200 and data:
                ext = EXT_BY_TYPE.get(ctype)
                if not ext:
                    m = re.search(r"\.(jpe?g|png|gif|webp|bmp)(?:$|\?)", img_url, re.I)
                    ext = (m.group(1).lower().replace("jpeg", "jpg") if m else "bin")
                name = f"{rid}_{seq}.{ext}"
                path = os.path.join(IMG_DIR, name)
                with open(path, "wb") as f:
                    f.write(data)
                try:  # 외부 주소를 거쳐 오는 이미지는 HTML 등 이미지가 아닌 응답일 때가 있다 -> 열리지 않으면 버린다
                    with Image.open(path) as chk:
                        chk.verify()
                except Exception:
                    os.remove(path)
                    row["status"] = "이미지 아님"
                    print(f"    [건너뜀] #{seq} 이미지가 아닌 응답: {img_url[:90]}")
                    manifest.append(row)
                    continue
                row["file"] = name
                row["width"], row["height"] = image_size(path)
                print(f"    {name}  {row['width']}x{row['height']}  {len(data) // 1024}KB")
            else:
                print(f"    [실패] #{seq} HTTP {status}: {img_url[:90]}")
            manifest.append(row)

    with open(MANIFEST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rec_idx", "seq", "file", "width", "height", "bytes", "status", "url"],
                           delimiter="\t")
        w.writeheader()
        w.writerows(manifest)
    with open(os.path.join(IMG_DIR, "skipped.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rec_idx", "reason"], delimiter="\t")
        w.writeheader()
        w.writerows(skipped)

    ok = sum(1 for r in manifest if r["file"])
    print(f"\n공고 {len(load_targets())}건 중 건너뜀 {len(skipped)}건 | 이미지 {ok}/{len(manifest)}장 저장")


if __name__ == "__main__":
    main()
