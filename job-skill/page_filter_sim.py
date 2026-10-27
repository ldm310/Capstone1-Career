"""
모의 실험: '필요 없는 페이지 빼기'. 긴 이미지는 LLM 과 같은 기준(높이 1.5W, 겹침 0.15W)으로 잘라 조각 하나를 페이지로 본다.
페이지마다 Tesseract 로 싸게 훑고 아래 규칙으로 뺄지 정한다. 애매하면 남긴다.

  빼기  : 공백 뺀 글자 30자 미만(사진·그림), 또는 DROP 낱말만 있고 KEEP 낱말·기술명이 없음
  남기기: KEEP 낱말이나 기술명(3자 이상)이 하나라도 있음 / 어느 쪽 낱말도 없음(애매)

결과: out/page_filter/index.html (조각별 확인용), slices.tsv, slices/*.jpg, tess/*.txt (로컬 전용)
실행: py -3.12 page_filter_sim.py      (Tesseract 결과는 tess/ 에 저장해 두고 다시 쓴다)
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import subprocess
import sys
import time

from PIL import Image

from common import HERE, IMG_DIR, OUT_DIR, images_by_posting, load_targets
from evaluate import COMMON_TECH, MULTIWORD, _bounded_regex, _is_ascii
from run_llm import tiles_for

EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA = os.path.join(HERE, "models", "tessdata")
PF = os.path.join(OUT_DIR, "page_filter")
LLM = "llm_gpt-5.6-terra"
KEEP = re.compile(r"자격|필수|우대|요건|requirement|preferred|qualification|경험|경력|역량|이런\s*분|함께\s*하고\s*싶|좋아요|"
                  r"알고\s*계시면|기술\s*스택|사용하는\s*기술|tech\s*stack|담당\s*업무|주요\s*업무|하게\s*될|모집\s*부문|해당\s*직무", re.I)
DROP = re.compile(r"복리\s*후생|복지|전형\s*절차|채용\s*절차|전형\s*안내|지원\s*방법|접수\s*방법|제출\s*서류|근무\s*조건|근무\s*형태|"
                  r"근무\s*시간|근무지|급여|유의\s*사항|연혁|수상|투자|benefit|휴가|건강\s*검진", re.I)
TECH = [w for w in sorted(set(COMMON_TECH) | set(MULTIWORD), key=len, reverse=True) if len(w) > 2]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def tech_spans(text: str) -> list[tuple[int, int]]:
    low = text.lower()
    spans = []
    for w in TECH:
        rx = _bounded_regex(w) if _is_ascii(w) else re.compile(re.escape(w.lower()))
        spans += [(m.start(), m.end()) for m in rx.finditer(low)]
    return spans


def decide(text: str) -> dict:
    keep = [m.group(0) for m in KEEP.finditer(text)]
    drop = [m.group(0) for m in DROP.finditer(text)]
    techs = sorted({text[a:b] for a, b in tech_spans(text)}, key=str.lower)
    n = len(re.sub(r"\s+", "", text))
    if n < 30:
        d, why = "빼기", "글자 거의 없음"
    elif keep or techs:
        d, why = "남기기", "요건 낱말·기술명 있음"
    elif drop:
        d, why = "빼기", "복지·절차·조건 낱말만 있음"
    else:
        d, why = "남기기", "애매(어느 낱말도 없음)"
    uniq = lambda xs: list(dict.fromkeys(re.sub(r"\s+", " ", x) for x in xs))
    return {"decision": d, "reason": why, "keep": uniq(keep), "drop": uniq(drop), "tech": techs, "chars": n}


def highlight(text: str) -> str:
    """KEEP=초록, DROP=빨강, 기술명=파랑으로 감싼 HTML (겹치면 앞선 종류 우선)."""
    spans = [(m.start(), m.end(), "keep") for m in KEEP.finditer(text)]
    spans += [(m.start(), m.end(), "drop") for m in DROP.finditer(text)]
    spans += [(a, b, "tech") for a, b in tech_spans(text)]
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    out, pos = [], 0
    for a, b, kind in spans:
        if a < pos:
            continue
        out.append(html.escape(text[pos:a]))
        out.append(f'<mark class="{kind}">{html.escape(text[a:b])}</mark>')
        pos = b
    out.append(html.escape(text[pos:]))
    return "".join(out)


def tesseract(png: bytes) -> tuple[str, float]:
    t = time.perf_counter()
    r = subprocess.run([EXE, "stdin", "stdout", "-l", "kor+eng", "--tessdata-dir", TESSDATA], input=png, capture_output=True)
    return r.stdout.decode("utf-8", "replace"), time.perf_counter() - t


def main() -> None:
    for d in ("slices", "tess"):
        os.makedirs(os.path.join(PF, d), exist_ok=True)
    calls = {}
    for line in open(os.path.join(OUT_DIR, LLM, "_calls.jsonl"), encoding="utf-8"):
        c = json.loads(line)
        calls[(c["file"], c["tile"])] = c
    titles = {t["rec_idx"]: t for t in load_targets()}
    data, rows = [], []
    for rid, imgs in images_by_posting().items():
        post = {"rec_idx": rid, "company": titles[rid]["company"], "title": titles[rid]["title"], "images": []}
        for im in imgs:
            img = Image.open(os.path.join(IMG_DIR, im["file"])).convert("RGB")
            spans = tiles_for(img)
            entry = {"file": im["file"], "size": f"{img.width}x{img.height}", "url": im["url"], "slices": []}
            for k, (y0, y1) in enumerate(spans, 1):
                stem = f"{os.path.splitext(im['file'])[0]}_t{k:02d}"
                crop = img.crop((0, y0, img.width, y1))
                tpath = os.path.join(PF, "tess", stem + ".txt")
                if os.path.exists(tpath):
                    tess, sec = open(tpath, encoding="utf-8").read(), None
                else:
                    buf = io.BytesIO()
                    crop.save(buf, "PNG")
                    tess, sec = tesseract(buf.getvalue())
                    open(tpath, "w", encoding="utf-8").write(tess)
                view = crop if crop.width <= 1000 else crop.resize((1000, round(crop.height * 1000 / crop.width)))
                view.save(os.path.join(PF, "slices", stem + ".jpg"), quality=85)
                llm = open(os.path.join(OUT_DIR, LLM, "_tiles", stem + ".txt"), encoding="utf-8").read()
                dec = decide(tess)
                c = calls.get((im["file"], k), {})
                s = {"id": stem, "k": k, "n": len(spans), "y0": y0, "y1": y1, **dec,
                     "in": c.get("input_tokens", 0), "out": c.get("output_tokens", 0),
                     "tess_html": highlight(tess.strip()), "llm_html": highlight(llm.strip())}
                entry["slices"].append(s)
                rows.append({"rec_idx": rid, "company": post["company"], "slice": stem, "y": f"{y0}-{y1}",
                             "decision": dec["decision"], "reason": dec["reason"], "keep_words": " ".join(dec["keep"]),
                             "drop_words": " ".join(dec["drop"]), "tech": " ".join(dec["tech"]), "chars": dec["chars"]})
                print(f"  {stem:<22} {dec['decision']:<4} {dec['reason']}" + (f"  ({sec:.1f}s)" if sec else ""), flush=True)
            post["images"].append(entry)
        data.append(post)

    with open(os.path.join(PF, "slices.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(PF, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", blob))
    n_drop = sum(r["decision"] == "빼기" for r in rows)
    print(f"조각 {len(rows)}개 중 빼기 {n_drop}개 -> out/page_filter/index.html")


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>페이지 빼기 확인</title>
<style>
:root{--bg:#f6f6f4;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2a5bd7;
--keep:#cdeccf;--drop:#f6cfcf;--tech:#cfe0ff;--okb:#e6f4e7;--dropb:#fbe9e9;--ambb:#f1f0ea;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--panel:#1f1f1d;--ink:#e9e8e3;--muted:#9a9993;--line:#34332f;--accent:#7ea2ff;
--keep:#24502a;--drop:#5c2626;--tech:#22385f;--okb:#1d2a1e;--dropb:#2e1c1c;--ambb:#262521;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Segoe UI","Malgun Gothic",sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center}
header h1{font-size:16px;margin:0}.legend mark{padding:0 4px}.small{color:var(--muted);font-size:12px}
.layout{display:flex}nav{width:240px;flex:none;border-right:1px solid var(--line);padding:8px;position:sticky;top:52px;height:calc(100vh - 52px);overflow:auto}
nav button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:6px;padding:6px 8px;color:inherit;font:inherit;cursor:pointer}
nav button.on{background:var(--panel);box-shadow:inset 3px 0 0 var(--accent)}nav small{display:block;color:var(--muted);font-size:12px}
main{flex:1;min-width:0;padding:12px 16px}h2{font-size:17px;margin:0 0 4px}h3{font-size:14px;margin:18px 0 6px}
.slice{display:grid;grid-template-columns:minmax(220px,1.1fr) 230px minmax(220px,1fr) minmax(220px,1fr);gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:12px}
.slice.빼기{border-left:5px solid #d24b4b}.slice.남기기{border-left:5px solid #3b9b4a}.slice.amb{border-left:5px solid #9a9993}
.imgbox,.txt{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:6px}.imgbox img{width:100%;display:block}
.txt pre{margin:0;padding:8px;white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,Consolas,"Malgun Gothic",monospace}
.colh{font-size:12px;color:var(--muted);margin-bottom:4px}.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-weight:600}
.badge.빼기{background:var(--dropb);color:#c03c3c}.badge.남기기{background:var(--okb);color:#2f8a3d}
.info p{margin:6px 0;font-size:12.5px}.info b{font-weight:600}.verdict label{display:block;font-size:13px;margin:3px 0}
.verdict input[type=text]{width:100%;margin-top:4px;padding:4px 6px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:inherit}
mark.keep{background:var(--keep);color:inherit}mark.drop{background:var(--drop);color:inherit}mark.tech{background:var(--tech);color:inherit}
textarea{width:100%;height:140px;font:12px ui-monospace,Consolas,monospace;background:var(--panel);color:inherit;border:1px solid var(--line);border-radius:6px;padding:6px}
@media (max-width:1100px){.slice{grid-template-columns:1fr 1fr}}@media (max-width:700px){.layout{display:block}nav{position:static;width:auto;height:auto}.slice{grid-template-columns:1fr}}
</style></head><body>
<header><h1>페이지 빼기 확인</h1>
<span class="legend small"><mark class="keep">남길 낱말</mark> <mark class="drop">뺄 낱말</mark> <mark class="tech">기술명</mark></span>
<span class="small">규칙: 글자 30자 미만 → 빼기 · 남길 낱말/기술명 있음 → 남기기 · 뺄 낱말만 있음 → 빼기 · 아무것도 없음 → 남기기(애매)</span>
<label class="small"><input type="checkbox" id="onlyDrop"> 빼기만 보기</label></header>
<div class="layout"><nav id="nav"></nav><main id="main"></main></div>
<script>
const DATA = __DATA__;
const KEY = "page_filter_verdicts_v1";
let V = {}; try { V = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let cur = 0;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function save(){ try { localStorage.setItem(KEY, JSON.stringify(V)); } catch (e) {} summary(); }
function nav(){
  $("nav").innerHTML = "";
  DATA.forEach((p, i) => {
    const all = p.images.flatMap(im => im.slices), d = all.filter(s => s.decision === "빼기").length;
    const checked = all.filter(s => V[s.id] && V[s.id].v).length;
    const b = document.createElement("button"); b.className = i === cur ? "on" : "";
    b.innerHTML = esc(p.company) + "<small>조각 " + all.length + " · 빼기 " + d + " · 확인 " + checked + "/" + all.length + "</small>";
    b.onclick = () => { cur = i; render(); window.scrollTo(0, 0); }; $("nav").appendChild(b);
  });
}
function words(label, xs){ return xs.length ? "<p><b>" + label + "</b> " + xs.map(esc).join(", ") + "</p>" : ""; }
function render(){
  nav();
  const p = DATA[cur], only = $("onlyDrop").checked;
  let h = "<h2>" + esc(p.company) + " — " + esc(p.title) + "</h2><div class='small'>rec_idx " + esc(p.rec_idx) +
    " · <a href='https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=" + esc(p.rec_idx) + "' target='_blank' rel='noopener'>사람인 공고 ↗</a></div>";
  p.images.forEach(im => {
    h += "<h3>" + esc(im.file) + " <span class='small'>(" + esc(im.size) + ", 조각 " + im.slices.length + "개) · <a href='" + esc(im.url) + "' target='_blank' rel='noopener'>원본 주소 ↗</a></span></h3>";
    im.slices.forEach(s => {
      if (only && s.decision !== "빼기") return;
      const amb = s.reason.startsWith("애매") ? " amb" : "", v = V[s.id] || {};
      h += "<section class='slice " + s.decision + amb + "' data-id='" + s.id + "'>" +
        "<div><div class='colh'>조각 " + s.k + "/" + s.n + " · y " + s.y0 + "–" + s.y1 + "</div><div class='imgbox'><img loading='lazy' src='slices/" + s.id + ".jpg' alt='" + s.id + "'></div></div>" +
        "<div class='info'><span class='badge " + s.decision + "'>" + s.decision + "</span><p>" + esc(s.reason) + " · 글자 " + s.chars + "자</p>" +
        words("남길 낱말:", s.keep) + words("뺄 낱말:", s.drop) + words("기술명:", s.tech) +
        "<p class='small'>LLM 이 조각: 입력 " + s.in + " · 출력 " + s.out + " 토큰</p>" +
        "<div class='verdict'><div class='colh'>내 확인</div>" +
        ["맞음", "틀림-남겨야 함", "틀림-빼도 됨"].map(o => "<label><input type='radio' name='v_" + s.id + "' value='" + o + "'" + (v.v === o ? " checked" : "") + "> " + o + "</label>").join("") +
        "<input type='text' placeholder='메모(선택)' value='" + esc(v.note || "") + "'></div></div>" +
        "<div><div class='colh'>판정에 쓴 글자 (Tesseract)</div><div class='txt'><pre>" + s.tess_html + "</pre></div></div>" +
        "<div><div class='colh'>참고: LLM이 읽은 글자</div><div class='txt'><pre>" + s.llm_html + "</pre></div></div></section>";
    });
  });
  h += "<h3>내 확인 결과 (판정이 틀렸다고 표시한 조각) — 이 칸을 복사해 Claude에게 붙여 주세요</h3><textarea id='out' readonly></textarea>" +
       "<div class='small'>표시는 이 브라우저에 저장됩니다(다른 브라우저·기기와 공유되지 않음).</div>";
  $("main").innerHTML = h;
  document.querySelectorAll(".slice").forEach(sec => {
    const id = sec.dataset.id;
    sec.querySelectorAll("input[type=radio]").forEach(r => r.onchange = () => { V[id] = Object.assign(V[id] || {}, {v: r.value}); save(); nav(); });
    sec.querySelector("input[type=text]").oninput = e => { V[id] = Object.assign(V[id] || {}, {note: e.target.value}); save(); };
  });
  summary();
}
function summary(){
  const el = $("out"); if (!el) return;
  const lines = ["조각\t판정\t내 확인\t메모"];
  let n = 0, wrong = 0, total = 0;
  DATA.forEach(p => p.images.forEach(im => im.slices.forEach(s => {
    total++;
    const v = V[s.id]; if (!v || !v.v) return; n++;
    if (v.v !== "맞음" || v.note) { if (v.v !== "맞음") wrong++; lines.push([s.id, s.decision, v.v, v.note || ""].join("\t")); }
  })));
  el.value = "확인한 조각 " + n + "/" + total + ", 틀림 " + wrong + "\n" + lines.join("\n");
}
$("onlyDrop").onchange = render;
render();
</script></body></html>
"""

if __name__ == "__main__":
    main()
