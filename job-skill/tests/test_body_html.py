"""db_load.body_html — 웹 상세 화면용 본문 HTML(사람인 본문 칸만, 위험한 부분은 빼고, 이미지 주소는 전체 주소로). 지어낸 본문."""
from __future__ import annotations

PAGE = ('<html><div class="user_content"><p onclick="x()">지어낸 자격요건</p>'
        '<table><tr><td>Java</td></tr></table>'
        '<img src="/img/a.png"><img src="loading.gif" data-src="https://cdn.example.com/b.jpg">'
        '<iframe src="https://x.example"></iframe><a href="javascript:alert(1)">링크</a><style>p{color:red}</style>'
        '</div><script>tail()</script></html>')


def test_body_html_keeps_layout_and_removes_dangerous_parts():
    import db_load
    b = db_load.body_html(PAGE, "55000001")
    assert "<p>지어낸 자격요건</p>" in b and "<table><tr><td>Java</td></tr></table>" in b   # 표·문단은 그대로
    for bad in ("script", "onclick", "iframe", "javascript:", "<style"):
        assert bad not in b.lower(), bad
    assert 'src="https://www.saramin.co.kr/img/a.png"' in b      # 상대 주소 → 전체 주소
    assert 'src="https://cdn.example.com/b.jpg"' in b            # 늦게 불러오는 이미지(data-src)는 진짜 주소로
    assert "loading.gif" not in b and not b.endswith("</div>")   # 본문 칸을 닫는 태그는 빼고


def test_body_html_none_without_body():
    import db_load
    assert db_load.body_html("<html>마감된 공고</html>", "1") is None
