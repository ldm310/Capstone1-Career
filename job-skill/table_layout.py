"""
'왼쪽 머리말 | 오른쪽 내용' 표의 칸 구조를 살려 OCR 줄 상자를 글자로 잇는다.

문제: 공고 표는 왼쪽 머리말(지원자격·우대사항 …)이 칸의 세로 가운데에 있다. 상자를 위에서부터만 이으면
      머리말이 그 칸 목록의 중간에 끼어(예: 8줄 우대사항 목록의 4번째 줄 뒤) LLM 이 칸 경계를 잘못 읽는다.
방법:
  1) 표 찾기: 왼쪽에 짧은 상자(머리말)가 세로로 2개 이상 있고, 그 오른쪽에 빈 세로 틈을 두고 내용이 있는 구간.
     틈을 가로지르는 상자(전체 폭 글)가 나오면 표가 끝난 것으로 본다.
  2) 칸 나누기: 이미지의 가로 테두리선을 우선 쓰고(글자 없는 얇은 줄인데 위아래와 색이 다름),
     테두리가 없으면 내용 줄 사이 간격이 평소보다 크게 벌어지는 곳을 칸 경계로 본다.
  3) 진짜 표만: 칸의 내용이 문장·목록처럼 길어야 표로 본다(복리후생 아이콘 격자처럼 짧은 낱말뿐인 칸은 제외).
     한 번 표로 쓴 상자는 다른 표에서 다시 쓰지 않는다.
  4) 머리말은 자기 칸 맨 앞에 '■ 머리말' 로 붙이고 그 칸 내용을 잇는다. 나머지 상자는 원래대로 위에서부터.
상자 형식: [x1, y1, x2, y2, text]
"""

from __future__ import annotations

import re
from statistics import median

import numpy as np

LABEL_MAX = 10        # 머리말 글자 수(공백 제외) 상한
CELL_MIN_LEN = 6      # 표 칸으로 인정할 내용 줄 길이(중앙값) 하한
HEAD_WORDS = re.compile(r"자격|우대|업무|조건|모집|지원|담당|요건|경력|전형|절차|근무|직무|부문|분야|환경|기술|필수|접수|서류|복리|혜택")


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def join_rows(boxes: list[list]) -> list[dict]:
    """세로로 절반 이상 겹치면 같은 행. 행 안에서는 왼쪽부터, 칸 사이가 글자 높이의 0.6배를 넘으면 ' | '.
    반환: [{y0, y1, text, boxes}]"""
    rows = []
    for b in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        if rows:
            r = rows[-1]
            ov = min(b[3], r["y1"]) - max(b[1], r["y0"])
            if ov >= 0.5 * min(b[3] - b[1], r["y1"] - r["y0"]):
                r["boxes"].append(b)
                r["y0"], r["y1"] = min(r["y0"], b[1]), max(r["y1"], b[3])
                continue
        rows.append({"y0": b[1], "y1": b[3], "boxes": [b]})
    for r in rows:
        line, prev = "", None
        for b in sorted(r["boxes"], key=lambda b: b[0]):
            if prev is not None:
                gap = b[0] - prev[2]
                line += " | " if gap > 0.6 * max(1, min(b[3] - b[1], prev[3] - prev[1])) else " "
            line += b[4].strip()
            prev = b
        r["text"] = line
    return rows


def _borders(gray, y0, y1, x0, x1, boxes) -> list[int]:
    """[y0, y1) 안의 가로 테두리선 y. 글자 상자가 덮지 않는 줄 중 위아래(±4px)와 평균 밝기가 6 이상 다른 얇은 줄."""
    if gray is None or y1 - y0 < 10:
        return []
    h = gray.shape[0]
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    band = gray[y0:y1, max(0, int(x0)):int(x1)].astype(np.float32)
    if band.size == 0:
        return []
    covered = np.zeros(y1 - y0, bool)
    for b in boxes:
        a, z = int(b[1]) - y0 - 3, int(b[3]) - y0 + 3  # 글자 둘레(흐린 가장자리)까지 덮은 것으로 본다
        if z > 0 and a < len(covered):
            covered[max(0, a):min(len(covered), z)] = True
    # 테두리: 글자 없는 줄 중, 표 폭의 60% 이상에서 3px 위·아래 줄과 밝기가 12 이상 다른 줄(가로로 길게 이어진 선)
    lines = []
    for i in range(3, band.shape[0] - 3):
        if covered[i]:
            continue
        up, dn = np.abs(band[i] - band[i - 3]), np.abs(band[i] - band[i + 3])
        if ((up >= 12) & (dn >= 12)).mean() >= 0.6:
            lines.append(y0 + i)
    merged = []
    for y in lines:
        if merged and y - merged[-1][-1] <= 2:
            merged[-1].append(y)
        else:
            merged.append([y])
    return [int(sum(g) / len(g)) for g in merged]


def _merge_labels(labels: list[list]) -> list[dict]:
    """세로로 붙은 머리말 상자(예: '자격요건' + '및 우대사항')는 한 머리말로."""
    out = []
    for b in sorted(labels, key=lambda b: b[1]):
        h = b[3] - b[1]
        if out and b[1] - out[-1]["y1"] <= 0.9 * h:
            out[-1]["text"] += " " + b[4].strip()
            out[-1]["y1"] = b[3]
            out[-1]["boxes"].append(b)
        else:
            out.append({"y0": b[1], "y1": b[3], "text": b[4].strip(), "boxes": [b]})
    return out


def _candidate_tables(boxes: list[list], W: int) -> list[dict]:
    """왼쪽 머리말 열 후보들(가로지르는 상자로 끊은 덩어리마다 하나)."""
    # 머리말 후보: 짧고 왼쪽에 있으며 글머리표(· - • □ …)로 시작하지 않는 상자(목록 줄은 머리말이 아니다)
    cands = [b for b in boxes if 1 <= len(_flat(b[4])) <= LABEL_MAX and b[2] <= 0.45 * W
             and not re.match(r"^[\s·•\-–—*▶▷※□■○●◆◇√✓]", b[4])]
    seen, out = set(), []
    for c in sorted(cands, key=lambda b: b[1]):
        if id(c) in seen:
            continue
        cx = (c[0] + c[2]) / 2
        col = sorted([d for d in cands if abs((d[0] + d[2]) / 2 - cx) <= 0.06 * W], key=lambda b: b[1])
        for d in col:
            seen.add(id(d))
        if len(col) < 2:
            continue
        lx1 = max(d[2] for d in col)
        right = [b for b in boxes if b[0] >= lx1 + 8]
        if not right:
            continue
        cx0 = min(b[0] for b in right)
        crossing = [b for b in boxes if b[0] < lx1 - 2 and b[2] > cx0 + 2]
        cur = [col[0]]
        for d in col[1:] + [None]:
            if d is None or any(cur[-1][3] <= x[1] and x[3] <= d[1] for x in crossing):
                if len(cur) >= 2:
                    top = max([x[3] for x in crossing if x[3] <= cur[0][1]], default=0)
                    bot = min([x[1] for x in crossing if x[1] >= cur[-1][3]], default=float("inf"))
                    out.append({"y0": top, "y1": bot, "lx1": lx1, "labels": cur})
                cur = [d] if d is not None else []
            else:
                cur.append(d)
    return out


def _layout(boxes: list[list], gray=None, width: int | None = None):
    """표 칸 목록과 표로 쓴 상자 id 집합. 칸: {y0, label(str|None), rows:[text]}"""
    if not boxes:
        return [], set()
    W = width or max(b[2] for b in boxes)
    used: set[int] = set()
    cells_out = []
    for tid, t in enumerate(sorted(_candidate_tables(boxes, W), key=lambda t: -len(t["labels"]))):
        labels = [b for b in t["labels"] if id(b) not in used]
        if len(labels) < 2:
            continue
        # 첫 머리말 줄에 다른 칸 머리말이 나란히 있으면('모집 구분 | 해당 직무 | 우대 사항') 위쪽 머리말 표다 -> 열 표에 맡긴다
        l0 = labels[0]
        same = [b for b in boxes if min(b[3], l0[3]) - max(b[1], l0[1]) >= 0.5 * min(b[3] - b[1], l0[3] - l0[1])]
        if len(same) >= 3 and sum(bool(COL_HEAD.search(_flat(b[4]))) and len(_flat(b[4])) <= HEAD_MAX
                                  and not BULLET.match(b[4]) for b in same) >= 2:
            continue
        lo = max(t["y0"], min(b[1] for b in labels) - 400)
        hi = min(t["y1"], max(b[3] for b in labels) + 400)
        content = [b for b in boxes if id(b) not in used and b[0] >= t["lx1"] + 8 and lo <= (b[1] + b[3]) / 2 <= hi]
        if not content:
            continue
        rows = join_rows(content)
        x0, x1 = min(b[0] for b in labels), max(b[2] for b in content)
        lines = _borders(gray, rows[0]["y0"] - 60, rows[-1]["y1"] + 60, x0, x1, labels + content)
        if lines:
            idx = [sum(1 for y in lines if y <= (r["y0"] + r["y1"]) / 2) for r in rows]
        else:
            gaps = [rows[i + 1]["y0"] - rows[i]["y1"] for i in range(len(rows) - 1)]
            pos = [g for g in gaps if g > 0]
            m = median(pos) if pos else 0
            hmed = median([r["y1"] - r["y0"] for r in rows])
            thr = max(1.8 * m, m + 0.6 * hmed)
            idx, k = [0], 0
            for g in gaps:
                k += g > thr
                idx.append(k)
        cells: dict[int, list[dict]] = {}
        for r, k in zip(rows, idx):
            cells.setdefault(k, []).append(r)
        spans = {k: (min(r["y0"] for r in rs), max(r["y1"] for r in rs)) for k, rs in cells.items()}
        lbl_of: dict[int, list[dict]] = {}
        if lines:
            # 테두리가 있으면: 머리말 상자를 칸 번호로 나눈 뒤 같은 칸 안에서만 합친다.
            # 내용 없는 칸의 머리말(표 위 제목 등)은 표에 넣지 않는다.
            by_cell: dict[int, list[list]] = {}
            for b in labels:
                by_cell.setdefault(sum(1 for y in lines if y <= (b[1] + b[3]) / 2), []).append(b)
            for k, bs in by_cell.items():
                if k in spans:
                    bs = sorted(bs, key=lambda b: b[1])
                    lbl_of[k] = [{"y0": bs[0][1], "y1": bs[-1][3], "text": " ".join(b[4].strip() for b in bs), "boxes": bs}]
        else:
            for L in _merge_labels(labels):
                mid = (L["y0"] + L["y1"]) / 2
                inside = [k for k, (a, z) in spans.items() if a - 2 <= mid <= z + 2]
                k = inside[0] if inside else min(spans, key=lambda c: min(abs(mid - spans[c][0]), abs(mid - spans[c][1])))
                lbl_of.setdefault(k, []).append(L)
        # 진짜 표 칸: 머리말이 6줄·40자 이하(예: '데이터 분석/ 엔지니어링 및 시스템 구축 엔지니어 (신입/경력)')이고
        # 내용이 문장·목록처럼 긴 칸. 정상 칸이 연속된 가장 긴 구간만 표로 쓴다(아이콘 격자는 아래 머리말 낱말 조건으로 거른다).
        def ok(k):
            Ls = lbl_of.get(k, [])
            return (bool(Ls) and sum(len(L["boxes"]) for L in Ls) <= 6 and sum(len(_flat(L["text"])) for L in Ls) <= 40
                    and median(len(_flat(r["text"])) for r in cells[k]) >= CELL_MIN_LEN)
        keys, run, best = sorted(cells), [], []
        for k in keys:
            run = run + [k] if ok(k) else []
            if len(run) > len(best):
                best = list(run)
        # 공고 표다운지: 머리말 중 2개 이상이 공고 머리말 낱말(자격·우대·업무 …)이어야 한다(아이콘 격자·로고 배치 제외)
        heads = [L["text"] for k in best for L in lbl_of.get(k, [])]
        if len(best) < 2 or sum(bool(HEAD_WORDS.search(_flat(h))) for h in heads) < 2:
            continue
        for k in sorted(cells):
            if k not in best:
                continue  # 표 밖 칸은 원래대로 위에서부터 잇는다
            label = " / ".join(L["text"] for L in lbl_of.get(k, [])) or None
            top = min([spans[k][0]] + [L["y0"] for L in lbl_of.get(k, [])])
            bot = max([spans[k][1]] + [L["y1"] for L in lbl_of.get(k, [])])
            cells_out.append({"y0": spans[k][0], "top": top, "bot": bot, "label": label, "tid": tid,
                              "rows": [r["text"] for r in cells[k]]})
            for r in cells[k]:
                used.update(id(b) for b in r["boxes"])
            for L in lbl_of.get(k, []):
                used.update(id(b) for b in L["boxes"])
    return cells_out, used


# ---- 위쪽 머리말 / 좌우로 나란한 열 ('열 표') -------------------------------------------------------------
# 예: '직무명 | 직무내용 | 자격요건 | 우대사항' 머리말 줄 아래로 칸이 세로로 이어지는 표, 'A형 … | B형 …' 처럼 좌우 두 열.
# 위에서부터 행 단위로 이으면 한 줄에 여러 칸의 글이 섞여(예: '정제·적재 | -Spark, Kafka …') 어느 칸 글인지 잃는다.
# 방법: 1) 머리말 줄 찾기 — 칸 머리말 낱말(COL_HEAD)이 2개 이상 있는 짧은 글들의 행.
#       2) 칸 나누기 — 머리말 줄 + 그 아래 몇 행에서 글자가 없는 세로 틈(GUTTER_MIN px 이상). 각 칸에 머리말 상자가 있어야 한다.
#          아래로 한 행씩 늘리다가 어떤 틈이 막히면(칸을 가로지르는 글) 표가 끝난 것으로 본다.
#       3) 덩어리 나누기 — 테두리선, 없으면 행 간격이 크게 벌어지는 곳. 덩어리 첫 행이 머리말 같으면 그 덩어리의 칸 머리말로 쓰고,
#          아니면 앞 덩어리의 머리말을 이어 쓴다(예: 직무별 행). 한 칸에만 글이 있는 마지막 덩어리는 표 밖으로 본다.
#       4) 덩어리마다 칸 순서대로 '■ 머리말' + 그 칸 글. 글머리표(-, · …)를 쓰는 칸은 글머리표 없이 이어지는 줄을 앞 줄에 붙인다.
COL_HEAD = re.compile(r"자격|우대|담당|업무|요건|필수|모집|채용|포지션|직무명|직무내용|역할|경력|신입|[A-ZＡ-Ｚ]형|트랙|부문|기술")
SECTION_NO = re.compile(r"^\s*0?\d{1,2}(\s|$|[.)])")
BULLET = re.compile(r"^\s*([-–—·•*▶▷※□■○●◆◇√✓]|\d{1,2}[.)]|[a-z][.)])")
GUTTER_MIN = 8        # 칸 사이 세로 틈 최소 폭(px)
GAP_STOP = 4          # 행 간격이 줄 높이의 이 배수를 넘으면 열 표가 끝난 것으로 본다
HEAD_MAX = 20         # 칸 머리말 상자 하나의 글자 수(공백 제외) 상한


def _gutters(bs: list[list]) -> list[tuple[float, float]]:
    """상자들이 가로로 덮지 않는 틈(왼쪽 끝~오른쪽 끝 사이)."""
    segs = sorted((b[0], b[2]) for b in bs)
    out, cur = [], list(segs[0])
    for a, z in segs[1:]:
        if a > cur[1]:
            if a - cur[1] >= GUTTER_MIN:
                out.append((cur[1], a))
            cur = [a, z]
        else:
            cur[1] = max(cur[1], z)
    return out


def _col_of(b, gs) -> int:
    c = (b[0] + b[2]) / 2
    return sum(1 for g in gs if (g[0] + g[1]) / 2 < c)


def _head_cells(row: dict, gs) -> dict[int, str] | None:
    """행이 칸 머리말 줄이면 {칸 번호: 머리말}. 칸 2개 이상, 모두 짧고, 머리말 낱말·번호가 2칸 이상."""
    cols: dict[int, list] = {}
    for b in sorted(row["boxes"], key=lambda b: b[0]):
        cols.setdefault(_col_of(b, gs), []).append(b[4].strip())
    if len(cols) < 2:
        return None
    texts = {k: " ".join(v) for k, v in cols.items()}
    if any(len(_flat(t)) > 1.5 * HEAD_MAX or BULLET.match(t) for t in texts.values()):  # 한 칸 머리말(상자 여러 개)은 30자까지, 글머리표면 내용 줄
        return None
    if sum(bool(COL_HEAD.search(_flat(t)) or SECTION_NO.match(t)) for t in texts.values()) < 2:
        return None
    return texts


def _sub_head(line: str) -> tuple[str, str] | None:
    """칸 첫 줄이 소제목이면 (소제목, 같은 줄의 나머지 글). '[우대사항] Spring 숙련자' -> ('[우대사항]', 'Spring 숙련자')"""
    m = re.match(r"^\s*([\[【〔<][^\]】〕>]{1,15}[\]】〕>])\s*(.*)$", line)
    if m and COL_HEAD.search(_flat(m.group(1))):
        return m.group(1), m.group(2)
    if len(_flat(line)) <= HEAD_MAX and not BULLET.match(line) and COL_HEAD.search(_flat(line)) and " | " not in line \
            and len(_flat(line)) <= 12:
        return line.strip(), ""
    return None


def _col_lines(bs: list[list]) -> list[str]:
    """한 칸의 상자 -> 줄. 글머리표를 쓰는 칸이면 글머리표 없는 줄을 앞 줄에 이어 붙인다(줄바꿈된 항목)."""
    lines = [r["text"] for r in join_rows(bs)] if bs else []
    if not any(BULLET.match(l) for l in lines):
        return lines
    out = []
    for l in lines:
        if out and not BULLET.match(l) and not _sub_head(l):  # 소제목('[우대사항]')은 앞 줄에 붙이지 않는다
            out[-1] += " " + l
        else:
            out.append(l)
    return out


def _column_tables(boxes: list[list], gray=None, width: int | None = None):
    """열 표 덩어리 목록, 쓴 상자 id, 표 세로 구간. 덩어리: (y0, [줄])"""
    rows = join_rows(boxes)
    blocks, used, zones, i = [], set(), [], 0
    while i < len(rows):
        # 1) 머리말 줄 후보: 상자 2개 이상, 머리말 낱말이 든 짧은 상자가 2개 이상
        hb = rows[i]["boxes"]
        if len(hb) < 2 or sum(bool(COL_HEAD.search(_flat(b[4]))) and len(_flat(b[4])) <= HEAD_MAX and not BULLET.match(b[4])
                              for b in hb) < 2:
            i += 1
            continue
        # 2) 칸: 머리말 줄 + 아래 3행으로 틈을 정하고, 각 칸에 머리말 상자가 있어야 한다
        if i + 3 >= len(rows):
            break
        gs = _gutters(hb + [b for r in rows[i + 1:i + 4] for b in r["boxes"]])
        keep, last = [], -1
        for g in gs:  # 머리말 상자가 없는 칸은 왼쪽 칸에 합친다
            if any(last < (b[0] + b[2]) / 2 < g[0] for b in hb):
                keep.append(g)
                last = g[1]
        if keep and not any((b[0] + b[2]) / 2 > keep[-1][1] for b in hb):
            keep.pop()
        if not keep:
            i += 1
            continue
        j, cov = i + 4, hb + [b for r in rows[i + 1:i + 4] for b in r["boxes"]]
        hq = median([r["y1"] - r["y0"] for r in rows[i:i + 4]])
        if any(rows[k + 1]["y0"] - rows[k]["y1"] > GAP_STOP * hq for k in range(i, i + 3)):
            i += 1
            continue
        while j < len(rows):  # 아래로 늘리다가 칸 사이 틈이 하나라도 막히거나 행 간격이 크게 벌어지면 멈춘다
            if rows[j]["y0"] - rows[j - 1]["y1"] > GAP_STOP * hq:
                break
            trial = cov + rows[j]["boxes"]
            now = _gutters(trial)
            if not all(any(min(g[1], n[1]) - max(g[0], n[0]) >= 1 for n in now) for g in keep):
                break
            cov, j = trial, j + 1
        region = rows[i:j]
        # 3) 덩어리: 테두리선, 없으면 큰 행 간격
        x0, x1 = min(b[0] for r in region for b in r["boxes"]), max(b[2] for r in region for b in r["boxes"])
        lines = _borders(gray, region[0]["y0"] - 5, region[-1]["y1"] + 5, x0, x1, [b for r in region for b in r["boxes"]])
        gaps = [region[k + 1]["y0"] - region[k]["y1"] for k in range(len(region) - 1)]
        pos = [g for g in gaps if g > 0]
        m = median(pos) if pos else 0
        hmed = median([r["y1"] - r["y0"] for r in region])
        thr = max(1.8 * m, m + 0.6 * hmed)
        bands, cur = [[region[0]]], [region[1]]  # 맨 위 머리말 줄은 따로 한 덩어리
        for k in range(2, len(region)):
            a, z = region[k - 1], region[k]
            # 테두리선이 있거나 행 간격이 크게 벌어지면 나눈다(덩어리 안에서 잘못 나뉘어도 칸 머리말은 이어 쓰므로 표시는 유지된다)
            split = any(a["y1"] - 2 <= y <= z["y0"] + 2 for y in lines) or gaps[k - 1] > thr
            if split:
                bands.append(cur)
                cur = []
            cur.append(z)
        bands.append(cur)
        # 한 칸에만 글이 있는 마지막 덩어리는 표 밖(예: 표 아래 '근무조건' 제목)
        ncol = lambda band: len({_col_of(b, keep) for r in band for b in r["boxes"]})
        # 마지막 덩어리가 한 행뿐이고 머리말 줄이 아니면 표 아래의 다른 글(예: '근무형태 | 정규직')로 본다
        while len(bands) > 2 and len(bands[-1]) == 1 and not _head_cells(bands[-1][0], keep):
            bands.pop()
        while len(bands) > 1 and ncol(bands[-1]) < 2:
            bands.pop()
        body = [b for band in bands for r in band[1:] for b in r["boxes"]]
        if len([r for band in bands for r in band]) < 4 or not body or \
                median(len(_flat(b[4])) for b in body) < CELL_MIN_LEN:
            i += 1
            continue
        # 4) 덩어리마다 칸 순서대로. 맨 위 머리말 줄의 머리말은 아래 덩어리들이 이어 쓴다(예: 직무별 행).
        #    중간에 자기 머리말 줄이 있는 덩어리가 나오면(예: '02 공통 자격요건 | 03 주요 기술') 그 덩어리는 자기 머리말을 쓰고,
        #    그 뒤로는 이어 쓰지 않는다(머리말이 표 칸 이름이 아니라 단락 제목이었던 것).
        table_heads: dict[int, str] = {}
        top_heads, top_shown = {}, set()   # 맨 위 머리말 줄: 아래에서 한 번도 안 쓰인 칸 머리말은 따로 내보낸다(글자 누락 방지)
        for bi, band in enumerate(bands):
            h = _head_cells(band[0], keep)
            content = band[1:] if h else band
            # 단락 나누기 보호 구간: 맨 위 머리말 + 그것을 이어 쓰는 덩어리들은 한 묶음(끊기면 머리말을 잃는다).
            # 중간의 자기 머리말 덩어리는 머리말에 자격·우대·업무 같은 낱말이 있을 때만 따로 보호한다
            # ('04 함께할 팀 | 05 근무조건' 같은 단락 제목 묶음까지 보호하면 원래 빼던 단락이 남게 된다).
            if bi == 0:
                table_heads = top_heads = h or {}
                zones.append([band[0]["y0"], band[-1]["y1"]])
                cur = zones[-1]
            elif h:
                table_heads = {}
                cur = None
                if any(COL_HEAD.search(_flat(t)) for t in h.values()):
                    zones.append([band[0]["y0"], band[-1]["y1"]])
            elif table_heads and cur is not None:
                cur[1] = band[-1]["y1"]
            heads = h or table_heads
            cols: dict[int, list] = {}
            for r in content:
                for b in r["boxes"]:
                    cols.setdefault(_col_of(b, keep), []).append(b)
            out = []
            own = set(h or {}) if bi > 0 else set()  # 중간 덩어리의 자기 머리말은 내용이 없어도 낸다(맨 위 머리말은 아래에서 씀)
            for k in sorted(set(cols) | own):
                lines = _col_lines(cols.get(k, []))
                sub = None if h else _sub_head(lines[0]) if lines else None
                if sub:  # 칸 첫 줄이 소제목(예: '[자격요건]')이면 물려받은 머리말 대신 그것을 쓴다
                    out.append("■ " + sub[0])
                    lines = ([sub[1]] if sub[1] else []) + lines[1:]
                elif heads.get(k):
                    out.append("■ " + heads[k])
                    if heads is top_heads:
                        top_shown.add(k)
                out += lines
            if out:
                blocks.append((band[0]["y0"], out))
            for r in band:
                used.update(id(b) for b in r["boxes"])
        rest = [top_heads[k] for k in sorted(top_heads) if k not in top_shown]
        if rest and bands:
            blocks.append((bands[0][0]["y0"], [" | ".join(rest)]))
        i += len([r for band in bands for r in band])
    return blocks, used, [tuple(z) for z in zones]


def table_text(boxes: list[list], gray=None, width: int | None = None) -> str:
    """상자 -> 글자. 왼쪽 머리말 표는 칸마다 '■ 머리말' + 내용, 열 표(위쪽 머리말·좌우 열)는 덩어리마다 칸 순서대로
    '■ 머리말' + 내용, 나머지는 위에서부터 행 단위."""
    cells, used = _layout(boxes, gray, width)
    blocks = [(c["y0"], (["■ " + c["label"]] if c["label"] else []) + c["rows"]) for c in cells]
    rest = [b for b in boxes if id(b) not in used]
    cblocks, cused, _ = _column_tables(rest, gray, width)
    blocks += cblocks
    for r in join_rows([b for b in rest if id(b) not in cused]):
        blocks.append((r["y0"], [r["text"]]))
    blocks.sort(key=lambda x: x[0])
    return "\n".join(line for _, ls in blocks for line in ls)


def table_zones(boxes: list[list], gray=None, width: int | None = None) -> list[tuple[float, float]]:
    """단락 나누기용: 표로 인식한 칸들의 세로 구간(이어진 칸은 하나로)과 열 표 구간. 이 구간 안에서는 단락을 자르지 않는다
    (칸 안의 '□ 자격 요건' 같은 소제목에서 잘리면 왼쪽 머리말과 내용이 갈라진다)."""
    cells, used = _layout(boxes, gray, width)
    _, _, czones = _column_tables([b for b in boxes if id(b) not in used], gray, width)
    by_table: dict[int, list[float]] = {}
    for c in cells:  # 같은 표의 칸은 칸 사이 여백과 관계없이 한 구간
        z = by_table.setdefault(c["tid"], [c["top"], c["bot"]])
        z[0], z[1] = min(z[0], c["top"]), max(z[1], c["bot"])
    return sorted([(z[0], z[1]) for z in by_table.values()] + czones)


def table_label_boxes(boxes: list[list], gray=None, width: int | None = None) -> list[list]:
    """단락 나누기용: 진짜 표의 머리말 상자들. 이 상자에서는 단락을 자르지 않는다(칸이 중간에 잘리지 않게)."""
    cells, used = _layout(boxes, gray, width)
    W = width or (max(b[2] for b in boxes) if boxes else 0)
    return [b for b in boxes if id(b) in used and len(_flat(b[4])) <= LABEL_MAX and b[2] <= 0.45 * W]
