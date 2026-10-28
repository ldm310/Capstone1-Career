"""
수정 확인 — Airflow ② 의 변경 감지 단계.

진행 공고마다 본문을 다시 받아(fetch_images.get: 간격 1.2초, 프로젝트 이름 UA) 지문을 DB 의 raw_hash 와 비교한다.
지문은 db_load.content_hash(보이는 글 + 본문 이미지 주소)라서, 요청마다 바뀌는 빈 <font color> 태그는 변경으로 치지 않는다.
  - changed : 지문이 다름 → <run_dir>/pages/<번호>.html 저장 + targets.tsv (다음 단계가 다시 추출)
  - closed  : 404 같은 응답, 또는 본문 칸(user_content)이 없음 → 마감
  - unchanged
  - error   : 연결 실패·5xx → 사람인 일시 장애일 수 있어 마감으로 치지 않고 건너뜀
결과는 <run_dir>/changes.json 에도 쓴다.
"""

from __future__ import annotations

import json
import os

import fetch_images
from collect import write_targets
from db_load import content_hash


def detect_changes(run_dir: str, rows: list[dict], get=fetch_images.get) -> dict[str, list[str]]:
    res = {"changed": [], "closed": [], "unchanged": [], "error": []}
    changed_rows = []
    pages = os.path.join(run_dir, "pages")
    for r in rows:
        no = r["rec_idx"]
        status, _, body = get(fetch_images.RELAY.format(id=no))
        if status is None or status >= 500:
            res["error"].append(no)
            continue
        page = body.decode("utf-8", "replace") if status == 200 else ""
        if status != 200 or "user_content" not in page:
            res["closed"].append(no)
            continue
        if content_hash(page, no) == r["raw_hash"]:
            res["unchanged"].append(no)
            continue
        os.makedirs(pages, exist_ok=True)
        with open(os.path.join(pages, f"{no}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        res["changed"].append(no)
        changed_rows.append(r)
    write_targets(run_dir, changed_rows)
    with open(os.path.join(run_dir, "changes.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return res
