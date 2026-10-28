"""
수정 확인 — Airflow ② 의 공고 고르기·변경 감지 단계.

select_recheck: 두 직무 목록 전체(collect.scan_lists)와 DB 진행 공고를 맞춰 본문을 다시 받을 공고만 고른다.
  - 목록의 '수정' 시각(늦게 잡은 값)이 마지막 확인 시각(last_checked_at)보다 뒤 → 확인
  - 목록에서 사라진 진행 공고 → 확인(본문이 없으면 마감)
  - 그 밖(등록만 했거나, 수정이 마지막 확인보다 앞) → 이미 본 본문이라 받지 않음
detect_changes: 고른 공고마다 본문을 다시 받아(fetch_images.get: 간격 1.2초, 프로젝트 이름 UA) 지문을 DB 의 raw_hash 와 비교한다.
지문은 db_load.content_hash(보이는 글 + 본문 이미지 주소)라서, 요청마다 바뀌는 빈 <font color> 태그는 변경으로 치지 않는다.
  - changed : 지문이 다름 → <run_dir>/pages/<번호>.html 저장 + targets.tsv (다음 단계가 다시 추출)
  - closed  : 404·410, 또는 200 인데 본문 칸(user_content)이 없음 → 마감
  - unchanged
  - error   : 그 밖(연결 실패·5xx·403·429 등) → 일시 장애나 막힘일 수 있어 마감으로 치지 않고 건너뜀(다음 ② 가 다시)
결과는 <run_dir>/changes.json 에도 쓴다.
"""

from __future__ import annotations

import datetime as dt
import json
import os

import fetch_images
from collect import parse_deadline, write_targets
from db_load import content_hash


def select_recheck(listed: dict[str, dict], rows: list[dict], today: dt.date) -> tuple[list[dict], dict[str, int]]:
    """(본문을 다시 받을 공고, 숫자). rows 는 db_queries.open_postings, listed 는 collect.scan_lists.
    수정된 공고는 목록의 마감일로 deadline 을 바꿔 둔다(읽을 수 없으면 DB 값) — 다시 저장할 때 연장된 마감일이 들어가게."""
    check, modified, gone = [], 0, 0
    for r in rows:
        it = listed.get(r["rec_idx"])
        if it is None:
            gone += 1
            check.append(r)
            continue
        at = it.get("updated_at")
        if at is None or at <= r["last_checked_at"]:
            continue
        modified += 1
        d = parse_deadline(it.get("deadline_text", ""), today)
        check.append({**r, "deadline": d.isoformat()} if d else r)
    return check, {"진행": len(rows), "수정": modified, "목록에 없음": gone}


def detect_changes(run_dir: str, rows: list[dict], get=fetch_images.get) -> dict[str, list[str]]:
    res = {"changed": [], "closed": [], "unchanged": [], "error": []}
    changed_rows = []
    pages = os.path.join(run_dir, "pages")
    for r in rows:
        no = r["rec_idx"]
        status, _, body = get(fetch_images.RELAY.format(id=no))
        if status in (404, 410):
            res["closed"].append(no)
            continue
        if status != 200:  # 연결 실패·5xx·403·429 등: 일시 장애나 막힘일 수 있어 마감(되돌릴 수 없음)으로 치지 않는다
            res["error"].append(no)
            continue
        page = body.decode("utf-8", "replace")
        if "user_content" not in page:
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
