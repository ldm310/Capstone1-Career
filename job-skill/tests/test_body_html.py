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


def test_body_html_removes_disguised_script_links():
    """따옴표 없이, 글자를 바꿔(&#106; = j), 사이에 탭을 넣어 쓴 javascript: 주소도 뺀다(웹이 본문을 그대로 띄우므로)."""
    import db_load
    page = ('<div class="user_content"><a href=javascript:alert(1)>a</a><a href="&#106;avascript:alert(2)">b</a>'
            '<a href="java&#9;script:alert(3)">c</a><a href=" JavaScript:alert(4)">d</a>'
            '<a href="https://www.saramin.co.kr/x">정상</a></div><script></script>')
    b = db_load.body_html(page, "1")
    assert "alert" not in b
    assert 'href="https://www.saramin.co.kr/x"' in b and ">정상</a>" in b
