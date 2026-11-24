"""Archive explicitly reviewed public university career books, preserving PDF page references."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from .evidence_archive import ArchiveHttp, now
from .errors import AccessRestricted, ParseError, FetchError
from .platforms.linkareer import AGENT
from .privacy import prose_text


# Reviewed official publication pages, not search snippets, forms, admissions or job advertisements.
SOURCES = [
    {'source': 'inu', 'external_id': 'career-it-2019-2024', 'publisher': '인천대학교 취업경력개발팀',
     'title': '정보기술대학 취업성공 및 현장실습 수기모음집', 'domain': 'IT_SW',
     'publication_url': 'https://www.inu.ac.kr/bbs/ese/917/404805/artclView.do',
     'download_url': 'https://www.inu.ac.kr/bbs/ese/917/356640/download'},
    {'source': 'inu', 'external_id': 'career-lifescience-2019-2024', 'publisher': '인천대학교 취업역량개발팀',
     'title': '생명과학기술대학 취업 및 현장실습 수기모음집', 'domain': 'LIFE_SCIENCE',
     'publication_url': 'https://www.inu.ac.kr/bbs/molbio/1884/404816/artclView.do',
     'download_url': 'https://www.inu.ac.kr/bbs/molbio/1884/356659/download'},
]


def pdf_fetch(http, url):
    parts = urlsplit(url)
    origin = 'https://' + parts.netloc
    if parts.scheme != 'https' or origin != 'https://www.inu.ac.kr' or parts.username or parts.password:
        raise AccessRestricted('Unreviewed university host')
    if origin not in http.robots:
        body, _, _ = http._fetch(origin + '/robots.txt', 500_000)
        parser = RobotFileParser()
        parser.parse(body.decode('utf-8', 'replace').splitlines())
        http.robots[origin] = parser
    if not http.robots[origin].can_fetch(AGENT, url):
        raise AccessRestricted()
    body, mime, _ = http._fetch(url, 50_000_000)
    if not body.startswith(b'%PDF-') or mime not in ('application/pdf', 'application/octet-stream'):
        raise ParseError('Expected public PDF, not an HTML login or download landing page')
    return body


def extract_pages(content):
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise ParseError('Encrypted publication')
    pages = []
    for number, page in enumerate(reader.pages, 1):
        # Escape markup characters: PDF text is plain text, not source HTML.
        text = page.extract_text() or ''
        cleaned = prose_text(text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        pages.append({'page': number, 'text': cleaned, 'characters': len(cleaned),
                      'extraction_status': 'TEXT_READY' if len(cleaned.strip()) >= 50 else 'OCR_PENDING'})
    return pages


def collect(output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    http = ArchiveHttp()
    documents = []
    for source in SOURCES:
        metadata_path = root / (source['external_id'] + '.json')
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if (root / metadata['pdf_path']).is_file() and (root / metadata['pages_path']).is_file():
                documents.append(metadata)
                continue
        try:
            content = pdf_fetch(http, source['download_url'])
            digest = hashlib.sha256(content).hexdigest()
            pdf_path, pages_path = digest + '.pdf', digest + '.pages.jsonl'
            (root / pdf_path).write_bytes(content)
            pages = extract_pages(content)
            with (root / pages_path).open('w', encoding='utf-8') as f:
                for page in pages:
                    f.write(json.dumps(page, ensure_ascii=False) + '\n')
            metadata = {**source, 'pdf_path': pdf_path, 'pages_path': pages_path,
                        'sha256': digest, 'bytes': len(content), 'pages': len(pages),
                        'text_characters': sum(p['characters'] for p in pages),
                        'ocr_pending_pages': sum(p['extraction_status'] == 'OCR_PENDING' for p in pages),
                        'material_type': 'CAREER_AND_INTERNSHIP_ANTHOLOGY', 'publisher_tier': 'OFFICIAL_UNIVERSITY',
                        'individual_cases_split': False, 'final_pass_verified': False, 'collected_at': now()}
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            documents.append(metadata)
            print(json.dumps({'university_document': {k: metadata[k] for k in
                  ('external_id', 'pages', 'bytes', 'text_characters', 'ocr_pending_pages')}}, ensure_ascii=True), flush=True)
        except AccessRestricted:
            print(json.dumps({'source': source['source'], 'status': 'BLOCKED_ACCESS_RESTRICTED'}), flush=True)
            break
        except (FetchError, ParseError, PdfReadError):
            print(json.dumps({'source': source['source'], 'status': 'FETCH_OR_PARSE_FAILED'}), flush=True)
    result = {'documents': documents, 'document_count': len(documents),
              'page_count': sum(d['pages'] for d in documents), 'network_requests': http.requests}
    (root / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.output)
    print(json.dumps({'document_count': result['document_count'], 'page_count': result['page_count']}))
