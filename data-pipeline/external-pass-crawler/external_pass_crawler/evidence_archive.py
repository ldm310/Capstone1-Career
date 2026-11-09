"""Public source archive before company/role matching; never writes to the application DB."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from .errors import AccessRestricted, FetchError, ParseError
from .platforms.linkareer import _NoRedirect, AGENT
from .platforms.linkareer_parser import parse_search, parse_detail
from .classification import canonical_role
from .privacy import prose_text

ORIGINS = {'jobkorea': 'https://www.jobkorea.co.kr', 'linkareer': 'https://linkareer.com'}
# Only article images from these source-owned hosts, never arbitrary embedded URLs.
IMAGE_ORIGINS = {'https://www.jobkorea.co.kr', 'https://file1.jobkorea.co.kr',
                 'https://file2.jobkorea.co.kr', 'https://linkareer.com',
                 'https://media.linkareer.com'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class ArchiveHttp:
    def __init__(self, interval=2, opener=None):
        self.interval = max(2, interval)
        self.opener = opener or build_opener(_NoRedirect())
        self.robots, self.last = {}, {}
        self.requests = 0

    def _fetch(self, url, limit):
        origin = 'https://' + urlsplit(url).netloc
        delay = self.interval
        if origin in self.robots:
            delay = max(delay, self.robots[origin].crawl_delay(AGENT) or 0)
        time.sleep(max(0, delay - (time.monotonic() - self.last.get(origin, -1e10))))
        self.last[origin] = time.monotonic()
        self.requests += 1
        try:
            with self.opener.open(Request(url, headers={'User-Agent': AGENT}), timeout=25) as r:
                if r.status != 200 or r.geturl() != url:
                    raise AccessRestricted()
                body = r.read(limit + 1)
                if len(body) > limit:
                    raise FetchError('Response too large')
                return body, r.headers.get_content_type(), r.headers.get_content_charset()
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code in (401, 403, 429):
                raise AccessRestricted() from None
            raise FetchError() from None
        except (URLError, OSError, TimeoutError):
            raise FetchError() from None

    def get(self, url, *, image=False):
        parts = urlsplit(url)
        origin = 'https://' + parts.netloc
        allowed = IMAGE_ORIGINS if image else set(ORIGINS.values())
        if parts.scheme != 'https' or origin not in allowed or parts.username or parts.password or parts.fragment:
            raise AccessRestricted('Unapproved source URL')
        if origin not in self.robots:
            body, _, _ = self._fetch(origin + '/robots.txt', 500_000)
            robot = RobotFileParser()
            robot.parse(body.decode('utf-8', 'replace').splitlines())
            self.robots[origin] = robot
        if not self.robots[origin].can_fetch(AGENT, url):
            raise AccessRestricted('ROBOTS_DENIED')
        body, content_type, encoding = self._fetch(url, 8_000_000 if image else 4_000_000)
        if image:
            signatures = {'image/png': body.startswith(b'\x89PNG\r\n\x1a\n'),
                          'image/jpeg': body.startswith(b'\xff\xd8\xff'),
                          'image/webp': body.startswith(b'RIFF') and body[8:12] == b'WEBP'}
            if not signatures.get(content_type):
                raise ParseError('Unsupported image')
            return body, content_type
        if content_type not in ('text/html', 'text/plain'):
            raise ParseError('Unexpected content type')
        soup = BeautifulSoup(body, 'html.parser', from_encoding=encoding)
        title = soup.title.get_text(' ', strip=True) if soup.title else ''
        if re.search(r'captcha|access denied|just a moment|접근\s*차단', title, re.I) or soup.select('iframe[src*="captcha"], form[action*="challenge"]'):
            raise AccessRestricted()
        return soup


def jobkorea_listing(soup):
    records = []
    for row in soup.select('.selfLists > li'):
        link = row.select_one('a[href*="/PassAssay/View/"], a[href*="/passassay/view/"]')
        if not link:
            continue
        match = re.search(r'/View/(\d+)', link['href'], re.I)
        if not match:
            continue
        fields = row.select('.field')
        company = row.select_one('.titTx')
        title = row.select_one('.tit')
        season = row.select_one('.career')
        records.append({'source': 'jobkorea', 'external_id': match[1],
            'url': ORIGINS['jobkorea'] + '/starter/PassAssay/View/' + match[1],
            'title': title.get_text(' ', strip=True) if title else '',
            'company_name': company.get_text(' ', strip=True) if company else None,
            'role_text': fields[-1].get_text(' ', strip=True) if fields else None,
            'season_text': season.get_text(' ', strip=True) if season else None,
            'material_type': 'PASS_ESSAY', 'pass_stage': 'UNSPECIFIED'})
    return records


def jobkorea_body(soup):
    body = soup.select_one('dl.qnaLists')
    if body is None:
        raise ParseError('Article body absent; do not archive navigation or login text')
    for extra in body.select('script,style,.skip,.txSpllChk,.advice'):
        extra.decompose()
    # Keep the submitted answers and questions, not applicant profile/spec/sidebar/comments.
    return prose_text(str(body)), [urljoin(ORIGINS['jobkorea'], img.get('src', ''))
                                  for img in body.select('img[src]')]


class Archive:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'bodies').mkdir(exist_ok=True)
        (self.root / 'images').mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.root / 'archive.sqlite3')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS document(source TEXT,external_id TEXT,payload TEXT NOT NULL,
                PRIMARY KEY(source,external_id));
            CREATE TABLE IF NOT EXISTS source_block(source TEXT PRIMARY KEY,code TEXT,at TEXT);
        ''')

    def has(self, record):
        return self.conn.execute('SELECT 1 FROM document WHERE source=? AND external_id=?',
                                 (record['source'], record['external_id'])).fetchone() is not None

    def blocked(self, source):
        return self.conn.execute('SELECT 1 FROM source_block WHERE source=?', (source,)).fetchone() is not None

    def block(self, source):
        with self.conn:
            self.conn.execute('INSERT OR REPLACE INTO source_block VALUES(?,?,?)',
                              (source, 'ACCESS_RESTRICTED', now()))

    def save(self, record, body, images=()):
        if (len(body.strip()) < 100 and not images) or len(body) > 200_000:
            raise ParseError('Empty, truncated or oversized article body')
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        relative = 'bodies/' + digest + '.txt'
        (self.root / relative).write_text(body, encoding='utf-8', newline='\n')
        payload = {**record, 'body_path': relative, 'body_sha256': digest, 'body_characters': len(body),
                   'image_assets': list(images), 'collected_at': now(), 'publisher_tier': 'ESTABLISHED_CAREER_PLATFORM',
                   'identity_verified': False, 'final_pass_verified': False,
                   'standard_role_code': canonical_role(record.get('role_text') or ''),
                   'company_id': None, 'extraction_status': 'PENDING', 'schema_version': 1,
                   'body_format': 'TEXT_AND_IMAGES' if images and len(body.strip()) >= 100 else
                                  'IMAGE' if images else 'TEXT'}
        with self.conn:
            self.conn.execute('INSERT INTO document VALUES(?,?,?)',
                              (record['source'], record['external_id'], json.dumps(payload, ensure_ascii=False)))
        return payload

    def export(self):
        rows = self.conn.execute('SELECT payload FROM document ORDER BY source,external_id').fetchall()
        with (self.root / 'manifest.jsonl').open('w', encoding='utf-8') as f:
            for (payload,) in rows:
                f.write(payload + '\n')
        columns = ('source', 'external_id', 'company_name', 'role_text', 'standard_role_code',
                   'season_text', 'body_characters', 'body_format', 'url', 'body_path')
        with (self.root / 'catalog.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for (payload,) in rows:
                record = json.loads(payload)
                values = [record.get(key) for key in columns]
                writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@'))
                                 else value for value in values])
        hashes = [json.loads(row[0])['body_sha256'] for row in rows]
        return {'documents': len(rows), 'unique_bodies': len(set(hashes)),
                'sources': dict(self.conn.execute('SELECT source,count(*) FROM document GROUP BY source').fetchall())}


def candidates(http, source, max_pages, keywords, jobkorea_keywords=None):
    seen = set()
    queries = keywords if source == 'linkareer' else (jobkorea_keywords or [''])
    for keyword in queries:
        query_seen = set()
        for page in range(1, max_pages + 1):
            total = None
            if source == 'jobkorea':
                params = {'Page': page}
                if keyword:
                    params['schTxt'] = keyword
                url = ORIGINS[source] + '/starter/passassay?' + urlencode(params)
                records = jobkorea_listing(http.get(url))
            else:
                url = ORIGINS[source] + '/cover-letter/search?' + urlencode(
                    {'keyword': keyword, 'page': page, 'sort': 'RELEVANCE', 'tab': 'all'})
                listing = parse_search(str(http.get(url)))
                total = listing.total
                records = [{'source': source, 'external_id': c.external_id,
                    'url': ORIGINS[source] + '/cover-letter/' + c.external_id,
                    'title': c.company + ' / ' + c.role, 'company_name': c.company,
                    'role_text': c.role, 'season_text': None, 'material_type': 'PASS_ESSAY',
                    'pass_stage': 'UNSPECIFIED'} for c in listing.candidates]
            fresh = [r for r in records if r['external_id'] not in query_seen]
            # Stop a repeated/empty page, never loop across identical page responses.
            if not fresh:
                break
            for record in fresh:
                query_seen.add(record['external_id'])
                if record['external_id'] in seen:
                    continue
                seen.add(record['external_id'])
                yield record
            if total is not None and len(query_seen) >= total:
                break


def run(args, http=None):
    http = http or ArchiveHttp(args.interval)
    archive = Archive(args.output)
    reports = []
    try:
        for source in args.sources:
            report = {'source': source, 'saved': 0, 'reused': 0, 'failed': 0, 'images': 0,
                      'filtered_non_it': 0, 'status': 'COMPLETED'}
            reports.append(report)
            if archive.blocked(source):
                report['status'] = 'BLOCKED_PREVIOUSLY'
                continue
            try:
                for record in candidates(http, source, args.max_pages, args.keywords,
                                         getattr(args, 'jobkorea_keywords', None)):
                    if archive.has(record):
                        report['reused'] += 1
                        continue
                    if getattr(args, 'it_only', False) and canonical_role(record.get('role_text') or '') is None:
                        report['filtered_non_it'] += 1
                        continue
                    if report['saved'] + report['failed'] >= args.max_documents:
                        report['status'] = 'LIMIT_REACHED'
                        break
                    try:
                        soup = http.get(record['url'])
                        if source == 'jobkorea':
                            body, image_urls = jobkorea_body(soup)
                        else:
                            detail = parse_detail(str(soup), record['external_id'])
                            if detail.company != record['company_name'] or detail.role != record['role_text']:
                                raise ParseError('Source identity changed between listing and detail')
                            body, image_urls = prose_text(detail.content), []
                        assets = []
                        for url in list(dict.fromkeys(image_urls))[:args.max_images]:
                            if 'https://' + urlsplit(url).netloc not in IMAGE_ORIGINS:
                                continue
                            content, mime = http.get(url, image=True)
                            digest = hashlib.sha256(content).hexdigest()
                            extension = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[mime]
                            relative = 'images/' + digest + extension
                            (archive.root / relative).write_bytes(content)
                            assets.append({'url': url, 'path': relative, 'sha256': digest, 'mime': mime,
                                           'ocr_status': 'PENDING'})
                        archive.save(record, body, assets)
                        report['saved'] += 1
                        report['images'] += len(assets)
                        if report['saved'] % 10 == 0:
                            archive.export()
                            print(json.dumps({'progress': report}, ensure_ascii=True), flush=True)
                    except (FetchError, ParseError):
                        report['failed'] += 1
            except AccessRestricted:
                archive.block(source)
                report['status'] = 'BLOCKED_ACCESS_RESTRICTED'
            except (FetchError, ParseError):
                report['status'] = 'LISTING_FAILED'
            print(json.dumps({'source_result': report}, ensure_ascii=True), flush=True)
        result = {'checked_at': now(), 'runs': reports, 'archive': archive.export(), 'network_requests': http.requests}
        (archive.root / 'last-run.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
    finally:
        archive.conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sources', nargs='+', choices=tuple(ORIGINS), default=list(ORIGINS))
    p.add_argument('--max-documents', type=int, default=200, help='Maximum new detail attempts per source')
    p.add_argument('--max-pages', type=int, default=20, help='Listing pages per source/search keyword')
    p.add_argument('--keywords', nargs='+', default=['백엔드', '프론트엔드', '개발', '데이터', '소프트웨어', '인프라'])
    p.add_argument('--jobkorea-keywords', nargs='+', help='Optional public schTxt searches instead of the general listing')
    p.add_argument('--it-only', action='store_true', help='Fetch details only for an unambiguous IT role in listing metadata')
    p.add_argument('--max-images', type=int, default=3)
    p.add_argument('--interval', type=float, default=2)
    args = p.parse_args(argv)
    if not (1 <= args.max_documents <= 2000 and 1 <= args.max_pages <= 100 and 0 <= args.max_images <= 10
            and 2 <= args.interval <= 60):
        p.error('Invalid bounded collection limits')
    result = run(args)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return int(any(r['status'] in ('BLOCKED_PREVIOUSLY', 'BLOCKED_ACCESS_RESTRICTED', 'LISTING_FAILED')
                   or r['failed'] for r in result['runs']))


if __name__ == '__main__':
    raise SystemExit(main())
