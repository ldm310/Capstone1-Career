"""common.images_by_posting — 받기에 실패한 이미지(파일 없음)는 넘기지 않는다(OCR 이 폴더를 열다 실패하지 않게)."""
from __future__ import annotations


def test_images_by_posting_skips_rows_without_file(monkeypatch):
    import common
    rows = [{"rec_idx": "A", "seq": "1", "file": "A_1.png", "status": "200"},
            {"rec_idx": "A", "seq": "2", "file": "", "status": "이미지 아님"},
            {"rec_idx": "B", "seq": "1", "file": "", "status": "404"},
            {"rec_idx": "C", "seq": "1", "file": "C_1.jpg", "status": "200"}]
    monkeypatch.setattr(common, "load_manifest", lambda: rows)
    got = common.images_by_posting()
    assert {k: [r["file"] for r in v] for k, v in got.items()} == {"A": ["A_1.png"], "C": ["C_1.jpg"]}
