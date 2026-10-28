"""
수정·마감 확인 — Airflow ① 매일 수집의 변경 감지 단계(예전 ② 수정 확인을 합침, 사용자 결정).

select_recheck: 두 직무 목록 전체(collect.scan_lists)와 DB 진행 공고를 맞춰 다시 볼 공고만 고른다.
  - "수정": 목록의 '수정' 시각(늦게 잡은 값)이 마지막 확인 시각(last_checked_at)보다 뒤 → 본문 확인
    (사람인은 '수정' 표시를 약 24시간만 보여 주므로 매일 본다)
  - "목록에 없음": 목록에서 사라진 진행 공고 → 마감 확인
  - 그 밖(등록만 했거나, 수정이 마지막 확인보다 앞) → 이미 본 본문이라 받지 않음
detect_changes: 고른 공고를 확인한다(fetch_images.get: 간격 1.2초, 프로젝트 이름 UA).
  - 목록에 없는 공고는 먼저 공고 전체 페이지(jobs/view)를 본다. 본문 페이지(view-detail)는 마감돼도 200·본문 그대로라
    마감을 알 수 없고, 전체 페이지에만 '접수마감'(sri_btn_expired_apply)·'마감되었습니다' 표시가 붙는다(2026-10-28 실제 확인).
  - 본문 지문은 db_load.content_hash(보이는 글 + 본문 이미지 주소) — 요청마다 바뀌는 빈 <font color> 태그는 변경으로 치지 않는다.
  결과
  - changed : 지문이 다름 → <run_dir>/pages/<번호>.html 저장 + targets.tsv 뒤에 붙임(이미 있는 번호는 안 넣음)
  - closed  : 전체 페이지에 마감 표시, 404·410, 또는 본문 칸(user_content)이 없음 → 마감
  - unchanged
  - error   : 그 밖(연결 실패·5xx·403·429 등) → 일시 장애나 막힘일 수 있어 마감으로 치지 않고 건너뜀(다음 날 다시)
결과는 <run_dir>/changes.json 에도 쓴다.
"""

from __future__ import annotations

import datetime as dt
import json
import os

import fetch_images
from collect import parse_deadline, read_targets, write_targets
from db_load import content_hash

VIEW = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={id}"
CLOSED_MARKS = ("sri_btn_expired_apply", "마감되었습니다")


def select_recheck(listed: dict[str, dict], rows: list[dict], today: dt.date) -> tuple[list[dict], dict[str, int]]:
    """(다시 볼 공고 + reason, 숫자). rows 는 db_queries.open_postings, listed 는 collect.scan_lists.
    수정된 공고는 목록의 마감일로 deadline 을 바꿔 둔다(읽을 수 없으면 DB 값) — 다시 저장할 때 연장된 마감일이 들어가게."""
    check, modified, gone = [], 0, 0
    for r in rows:
        it = listed.get(r["rec_idx"])
        if it is None:
            gone += 1
            check.append({**r, "reason": "목록에 없음"})
            continue
        at = it.get("updated_at")
        if at is None or at <= r["last_checked_at"]:
            continue
        modified += 1
        d = parse_deadline(it.get("deadline_text", ""), today)
        check.append({**r, "reason": "수정", **({"deadline": d.isoformat()} if d else {})})
    return check, {"진행": len(rows), "수정": modified, "목록에 없음": gone}


def _status_text(status) -> str:
    return "연결 실패" if status is None else f"HTTP {status}"


def _closed_by_view(no: str, get) -> tuple[bool | None, str]:
    """공고 전체 페이지로 마감인지. (True 마감 / False 진행 중 / None 모름(막힘·장애), 모를 때 원인)."""
    status, _, body = get(VIEW.format(id=no))
    if status in (404, 410):
        return True, ""
    if status != 200:
        return None, _status_text(status) + "(전체 페이지)"
    page = body.decode("utf-8", "replace")
    return any(m in page for m in CLOSED_MARKS), ""


def detect_changes(run_dir: str, rows: list[dict], get=fetch_images.get) -> dict[str, list[str]]:
    res = {"changed": [], "closed": [], "unchanged": [], "error": [], "why": {}}
    changed_rows = []
    pages = os.path.join(run_dir, "pages")
    for r in rows:
        no = r["rec_idx"]
        if r.get("reason") == "목록에 없음":
            closed, why = _closed_by_view(no, get)
            if closed is None:
                res["error"].append(no)
                res["why"][no] = why
                continue
            if closed:
                res["closed"].append(no)
                continue
        status, _, body = get(fetch_images.RELAY.format(id=no))
        if status in (404, 410):
            res["closed"].append(no)
            continue
        if status != 200:  # 연결 실패·5xx·403·429 등: 일시 장애나 막힘일 수 있어 마감(되돌릴 수 없음)으로 치지 않는다
            res["error"].append(no)
            res["why"][no] = _status_text(status)
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
    have = read_targets(run_dir)
    seen = {t["rec_idx"] for t in have}
    write_targets(run_dir, have + [r for r in changed_rows if r["rec_idx"] not in seen])
    with open(os.path.join(run_dir, "changes.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return res
