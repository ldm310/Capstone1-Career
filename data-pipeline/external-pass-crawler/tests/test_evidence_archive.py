import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from external_pass_crawler.evidence_archive import Archive, ArchiveHttp, candidates, jobkorea_body, jobkorea_listing, run
from external_pass_crawler.errors import AccessRestricted, ParseError
from external_pass_crawler.models import Candidate, SearchPage


LISTING = '''<ul class="selfLists"><li><p class="tit"><a href="/starter/PassAssay/View/12?Page=1">
<span class="titTx">예시회사</span><span class="career">2025 하반기</span>
<span class="field">신입</span><span class="field">백엔드개발자</span></a></p></li></ul>'''
BODY = '<dl class="qnaLists"><dt>개발 경험?</dt><dd><div class="tx">' + 'Spring으로 API를 구현했습니다. ' * 15 + '</div></dd></dl>'


class EvidenceArchiveTests(unittest.TestCase):
    def soup(self, text):
        return BeautifulSoup(text, 'html.parser')

    def test_listing_keeps_unknown_company_without_application_db_and_no_final_pass_promotion(self):
        record = jobkorea_listing(self.soup(LISTING))[0]
        self.assertEqual(record['company_name'], '예시회사')
        self.assertEqual(record['role_text'], '백엔드개발자')
        self.assertEqual(record['url'], 'https://www.jobkorea.co.kr/starter/PassAssay/View/12')
        self.assertEqual(record['pass_stage'], 'UNSPECIFIED')

    def test_body_excludes_profile_sidebar_and_masks_contacts(self):
        soup = self.soup('<aside>학교 프로필 비밀</aside>' + BODY.replace('</div>', ' a@example.com 010-1234-5678</div>'))
        body, images = jobkorea_body(soup)
        self.assertNotIn('학교 프로필', body)
        self.assertNotIn('a@example.com', body)
        self.assertNotIn('010-1234-5678', body)
        self.assertEqual(images, [])

    def test_missing_body_cannot_archive_login_navigation(self):
        with self.assertRaises(ParseError):
            jobkorea_body(self.soup('<body>로그인하세요' * 50))

    def test_hash_dedup_and_image_only_metadata(self):
        with TemporaryDirectory() as directory:
            archive = Archive(directory)
            self.addCleanup(archive.conn.close)
            record = jobkorea_listing(self.soup(LISTING))[0]
            body, _ = jobkorea_body(self.soup(BODY))
            archive.save(record, body)
            saved = json.loads(archive.conn.execute('SELECT payload FROM document').fetchone()[0])
            self.assertEqual(hashlib.sha256((Path(directory) / saved['body_path']).read_bytes()).hexdigest(),
                             saved['body_sha256'])
            archive.save({**record, 'external_id': '13'}, body)
            self.assertEqual(archive.export()['unique_bodies'], 1)
            self.assertEqual(len(list((Path(directory) / 'bodies').glob('*.txt'))), 1)
            payload = archive.save({**record, 'external_id': '14'}, '', [{'path': 'images/example.png'}])
            self.assertEqual(payload['body_format'], 'IMAGE')
            self.assertFalse(payload['final_pass_verified'])
            with self.assertRaises(ParseError):
                archive.save({**record, 'external_id': '15'}, '로그인')
            archive.conn.close()

    def test_repeated_page_stops_discovery(self):
        http = Mock()
        http.get.return_value = self.soup(LISTING)
        self.assertEqual(len(list(candidates(http, 'jobkorea', 20, []))), 1)
        self.assertEqual(http.get.call_count, 2)

    def test_keyword_overlap_does_not_hide_later_new_pages(self):
        http = Mock()
        first = self.soup(LISTING)
        second = self.soup(LISTING.replace('/12?', '/13?'))
        http.get.side_effect = [first, first, second, first]
        rows = list(candidates(http, 'jobkorea', 2, [], ['서버', '웹']))
        self.assertEqual({r['external_id'] for r in rows}, {'12', '13'})
        self.assertIn('schTxt=', http.get.call_args_list[0].args[0])

    def test_linkareer_stops_at_total_and_continues_next_keyword(self):
        http = Mock()
        http.get.return_value = self.soup('<html></html>')
        listing = SearchPage((Candidate('1', '예시', '백엔드'),), 1)
        with patch('external_pass_crawler.evidence_archive.parse_search', return_value=listing):
            rows = list(candidates(http, 'linkareer', 30, ['백엔드', '서버']))
        self.assertEqual(len(rows), 1)
        self.assertEqual(http.get.call_count, 2)

    def test_resume_reuses_article_without_detail_request(self):
        with TemporaryDirectory() as directory:
            args = SimpleNamespace(output=directory, sources=['jobkorea'], max_pages=1,
                                   max_documents=10, max_images=0, keywords=[], interval=2)
            http = Mock(requests=2)
            http.get.side_effect = [self.soup(LISTING), self.soup(BODY)]
            self.assertEqual(run(args, http)['archive']['documents'], 1)
            http = Mock(requests=1)
            http.get.return_value = self.soup(LISTING)
            result = run(args, http)
            self.assertEqual(result['runs'][0]['reused'], 1)
            http.get.assert_called_once()
            manifest = json.loads((Path(directory) / 'manifest.jsonl').read_text(encoding='utf-8'))
            self.assertTrue((Path(directory) / manifest['body_path']).is_file())

    def test_it_mode_filters_listing_roles_before_fetching_details(self):
        record = jobkorea_listing(self.soup(LISTING))[0]
        with TemporaryDirectory() as directory:
            args = SimpleNamespace(output=directory, sources=['jobkorea'], max_pages=1,
                                   max_documents=10, max_images=0, keywords=[], interval=2, it_only=True)
            http = Mock(requests=1)
            http.get.return_value = self.soup(BODY)
            with patch('external_pass_crawler.evidence_archive.candidates', return_value=iter([
                    {**record, 'external_id': '13', 'role_text': '영업관리'}, record])):
                result = run(args, http)
            self.assertEqual(result['runs'][0]['filtered_non_it'], 1)
            self.assertEqual(result['archive']['documents'], 1)
            http.get.assert_called_once_with(record['url'])

    def test_access_restriction_is_persistent_and_not_retried(self):
        with TemporaryDirectory() as directory:
            args = SimpleNamespace(output=directory, sources=['jobkorea'], max_pages=1,
                                   max_documents=10, max_images=0, keywords=[], interval=2)
            http = Mock(requests=1)
            http.get.side_effect = AccessRestricted()
            self.assertEqual(run(args, http)['runs'][0]['status'], 'BLOCKED_ACCESS_RESTRICTED')
            http = Mock(requests=0)
            self.assertEqual(run(args, http)['runs'][0]['status'], 'BLOCKED_PREVIOUSLY')
            http.get.assert_not_called()

    def test_unknown_host_credentials_and_non_https_never_fetch(self):
        http = ArchiveHttp(opener=Mock())
        for url in ('http://www.jobkorea.co.kr/x', 'https://evil.invalid/x',
                    'https://user:secret@www.jobkorea.co.kr/x', 'https://127.0.0.1/x'):
            with self.assertRaises(AccessRestricted):
                http.get(url)
        http.opener.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
