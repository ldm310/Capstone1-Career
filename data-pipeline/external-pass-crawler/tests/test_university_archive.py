import io
import unittest
from unittest.mock import Mock
from pypdf import PdfWriter
from external_pass_crawler.university_archive import extract_pages, pdf_fetch
from external_pass_crawler.errors import AccessRestricted, ParseError


class UniversityArchiveTests(unittest.TestCase):
    def test_scanned_or_blank_page_preserves_page_reference_for_ocr(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = io.BytesIO()
        writer.write(output)
        pages = extract_pages(output.getvalue())
        self.assertEqual(pages, [{'page': 1, 'text': '', 'characters': 0, 'extraction_status': 'OCR_PENDING'}])

    def test_encrypted_pdf_is_not_bypassed(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt('private')
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaises(ParseError):
            extract_pages(output.getvalue())

    def test_unreviewed_host_is_not_requested(self):
        http = Mock()
        with self.assertRaises(AccessRestricted):
            pdf_fetch(http, 'https://unreviewed.example.edu/book.pdf')
        http._fetch.assert_not_called()

    def test_html_login_response_cannot_be_saved_as_pdf(self):
        http = Mock()
        http.robots = {'https://www.inu.ac.kr': Mock()}
        http.robots['https://www.inu.ac.kr'].can_fetch.return_value = True
        http._fetch.return_value = (b'<html>login</html>', 'text/html', 'utf-8')
        with self.assertRaises(ParseError):
            pdf_fetch(http, 'https://www.inu.ac.kr/book.pdf')
