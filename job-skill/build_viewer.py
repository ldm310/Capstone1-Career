"""
OCR 후보별 추출 글자를 한곳에 모은 보기 파일을 만든다(로컬 전용, out/ 은 .gitignore 대상).

  out/ocr_texts.html : 공고를 고르면 원본 이미지와 후보별 글자를 나란히 보여 준다. 검색어 강조, 스크롤 맞추기.
  out/ocr_texts.md   : 같은 내용을 공고 -> 후보 순서로 이어 쓴 문서.

실행: py -3.12 build_viewer.py
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

from common import OUT_DIR, images_by_posting, load_targets

POSTING = "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={id}"
RELAY = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={id}&rec_seq=0"
CANDS = [
    ("tesseract", "Tesseract", "5.5.0 · kor+eng · tessdata_best · 원본 통째로"),
    ("easyocr", "EasyOCR", "1.7.2 · ko+en · CPU · 2000px/겹침300 분할"),
    ("paddleocr", "PaddleOCR", "3.7.0 · korean(PP-OCRv5) · CPU · 2000px/겹침300 분할"),
    ("llm_gpt-5.6-terra", "LLM gpt-5.6-terra", "B 방식 · detail high · 추론 none · 1.5W/겹침0.15W 분할"),
]
LLM_PRICE = (2.00, 12.00)  # USD / 1M 토큰 (입력, 출력)


def seconds_by_posting(cand: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    path = os.path.join(OUT_DIR, cand, "_timing.tsv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out[r["rec_idx"]] += float(r["seconds"])
    return out


def llm_usage(cand: str) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})
    path = os.path.join(OUT_DIR, cand, "_calls.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            c = json.loads(line)
            u = out[c["rec_idx"]]
            u["calls"] += 1
            u["in"] += int(c["input_tokens"])
            u["out"] += int(c["output_tokens"])
    return out


def collect() -> list[dict]:
    imgs = images_by_posting()
    secs = {c: seconds_by_posting(c) for c, _, _ in CANDS}
    usage = {c: llm_usage(c) for c, _, _ in CANDS if c.startswith("llm_")}
    data = []
    for t in load_targets():
        rid = t["rec_idx"]
        texts = []
        for c, label, setting in CANDS:
            p = os.path.join(OUT_DIR, c, f"{rid}.txt")
            text = open(p, encoding="utf-8").read() if os.path.exists(p) else "(출력 없음)"
            meta = f"{secs[c].get(rid, 0):.1f}초"
            if c in usage and rid in usage[c]:
                u = usage[c][rid]
                usd = u["in"] / 1e6 * LLM_PRICE[0] + u["out"] / 1e6 * LLM_PRICE[1]
                meta += f" · 호출 {u['calls']}회 · ${usd:.4f}"
            texts.append({"key": c, "label": label, "setting": setting, "meta": meta,
                          "file": f"{c}/{rid}.txt", "text": text})
        data.append({"rec_idx": rid, "company": t["company"], "title": t["title"],
                     "posting": POSTING.format(id=rid), "relay": RELAY.format(id=rid),
                     "images": [{"file": i["file"], "url": i["url"], "size": f"{i['width']}x{i['height']}"}
                                for i in imgs.get(rid, [])],
                     "texts": texts})
    return data


HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OCR 추출 글자 비교</title>
<style>
:root{--bg:#f6f6f4;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2a5bd7;--mark:#ffe58a;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--panel:#1f1f1d;--ink:#e9e8e3;--muted:#9a9993;--line:#34332f;--accent:#7ea2ff;--mark:#6b5a12;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}
header h1{font-size:16px;margin:0}
header .note{color:var(--muted);font-size:12px}
.layout{display:flex;min-height:calc(100vh - 50px)}
nav{width:260px;flex:none;border-right:1px solid var(--line);padding:8px;overflow:auto;max-height:calc(100vh - 50px)}
nav button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:6px;padding:7px 8px;color:inherit;font:inherit;cursor:pointer}
nav button small{display:block;color:var(--muted);font-size:12px}
nav button.on{background:var(--panel);box-shadow:inset 3px 0 0 var(--accent)}
main{flex:1;min-width:0;padding:12px 16px}
.head h2{font-size:17px;margin:0 0 4px}
.links{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;margin-bottom:8px}
.links a{color:var(--accent)}
.imgs{font-size:12px;color:var(--muted);margin:0 0 8px;padding-left:18px}
.imgs a{color:var(--accent)}
.bar{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin-bottom:10px;font-size:13px}
.bar input[type=search]{padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:inherit;min-width:220px}
.cols{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}
.col{flex:1 0 250px;min-width:250px;background:var(--panel);border:1px solid var(--line);border-radius:8px;display:flex;flex-direction:column}
.col.img{flex:1.2 0 260px}
.col h3{margin:0;padding:8px 10px 6px;font-size:13px;border-bottom:1px solid var(--line)}
.col h3 small{display:block;font-weight:400;color:var(--muted);font-size:11.5px}
.col h3 .hits{float:right;font-weight:600;color:var(--accent)}
.body{height:calc(100vh - 290px);min-height:320px;overflow:auto;padding:8px 10px}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font:12.5px/1.55 ui-monospace,Consolas,"D2Coding","Malgun Gothic",monospace}
.body img{width:100%;display:block;margin-bottom:6px}
mark{background:var(--mark);color:inherit;border-radius:2px}
@media (max-width:760px){.layout{flex-direction:column}nav{width:auto;max-height:none;border-right:0;border-bottom:1px solid var(--line);display:flex;overflow-x:auto}nav button{min-width:180px}}
</style></head><body>
<header><h1>OCR 추출 글자 비교</h1>
<span class="note">로컬 전용 — 받은 이미지·공고 내용은 외부에 다시 게시하지 않는다. 원문 파일: ocr_test/out/&lt;후보&gt;/&lt;rec_idx&gt;.txt</span></header>
<div class="layout"><nav id="nav"></nav><main>
<div class="head" id="head"></div>
<div class="bar" id="bar"><input type="search" id="q" placeholder="검색어 강조 (예: Spring, 우대)">
<label><input type="checkbox" id="sync" checked> 스크롤 맞추기</label><span id="toggles"></span></div>
<div class="cols" id="cols"></div>
</main></div>
<script>
const DATA = __DATA__;
const shown = {img:true}; DATA[0].texts.forEach(t => shown[t.key] = true);
let cur = 0;
const $ = id => document.getElementById(id);
function esc(s){return s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function marked(text, q){
  if(!q) return [esc(text), 0];
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"), "gi");
  let n = 0, out = "", last = 0, m;
  while((m = re.exec(text))){ out += esc(text.slice(last, m.index)) + "<mark>" + esc(m[0]) + "</mark>"; last = m.index + m[0].length; n++; if(!m[0].length) re.lastIndex++; }
  return [out + esc(text.slice(last)), n];
}
function nav(){
  $("nav").innerHTML = "";
  DATA.forEach((d,i)=>{const b=document.createElement("button");b.className=i===cur?"on":"";
    b.innerHTML=esc(d.company)+"<small>"+esc(d.rec_idx)+" · "+esc(d.title)+"</small>";b.onclick=()=>{cur=i;render();};$("nav").appendChild(b);});
}
function toggles(){
  const items=[["img","원본 이미지"]].concat(DATA[0].texts.map(t=>[t.key,t.label]));
  $("toggles").innerHTML=""; items.forEach(([k,l])=>{const lab=document.createElement("label");lab.style.marginRight="10px";
    const c=document.createElement("input");c.type="checkbox";c.checked=shown[k];c.onchange=()=>{shown[k]=c.checked;cols();};
    lab.append(c," "+l);$("toggles").appendChild(lab);});
}
function head(){
  const d=DATA[cur];
  $("head").innerHTML="<h2>"+esc(d.company)+" — "+esc(d.title)+"</h2>"+
    '<div class="links"><a href="'+esc(d.posting)+'" target="_blank" rel="noopener">사람인 공고 페이지 ↗</a>'+
    '<a href="'+esc(d.relay)+'" target="_blank" rel="noopener">추출한 본문(relay) ↗</a><span>rec_idx '+esc(d.rec_idx)+'</span></div>'+
    '<ol class="imgs">'+d.images.map(im=>'<li>'+esc(im.file)+' ('+esc(im.size)+') · <a href="../images/'+encodeURIComponent(im.file)+'" target="_blank">로컬 파일</a> · <a href="'+esc(im.url)+'" target="_blank" rel="noopener">이미지 원본 주소 ↗</a></li>').join("")+'</ol>';
}
function cols(){
  const d=DATA[cur], q=$("q").value.trim(); $("cols").innerHTML="";
  if(shown.img){const c=document.createElement("section");c.className="col img";
    c.innerHTML="<h3>원본 이미지<small>"+d.images.length+"장 · 세로로 길면 스크롤</small></h3>";
    const b=document.createElement("div");b.className="body";
    d.images.forEach(im=>{const i=document.createElement("img");i.loading="lazy";i.src="../images/"+encodeURIComponent(im.file);i.alt=im.file;b.appendChild(i);});
    c.appendChild(b);$("cols").appendChild(c);}
  d.texts.forEach(t=>{ if(!shown[t.key]) return;
    const [html,n]=marked(t.text,q); const c=document.createElement("section");c.className="col";
    c.innerHTML="<h3>"+(q?'<span class="hits">'+n+'</span>':"")+esc(t.label)+"<small>"+esc(t.setting)+"</small><small>"+esc(t.meta)+" · "+t.text.replace(/\s/g,"").length.toLocaleString()+"자 · "+esc(t.file)+"</small></h3>";
    const b=document.createElement("div");b.className="body";b.innerHTML="<pre>"+html+"</pre>";c.appendChild(b);$("cols").appendChild(c);});
  const bodies=[...document.querySelectorAll(".body")]; let lock=false;
  bodies.forEach(b=>b.addEventListener("scroll",()=>{ if(!$("sync").checked||lock) return; lock=true;
    const r=b.scrollTop/Math.max(1,b.scrollHeight-b.clientHeight);
    bodies.forEach(o=>{if(o!==b) o.scrollTop=r*(o.scrollHeight-o.clientHeight);}); requestAnimationFrame(()=>lock=false);}));
}
function render(){nav();head();cols();}
$("q").addEventListener("input",cols); toggles(); render();
</script></body></html>
"""


def write_md(data: list[dict], path: str) -> None:
    lines = ["# OCR 추출 글자 (후보별)", "",
             "로컬 전용. 받은 이미지·공고 내용은 외부에 다시 게시하지 않는다. 나란히 보기는 `ocr_texts.html`.", "",
             "| 후보 | 설정 |", "|---|---|"]
    lines += [f"| {label} | {setting} |" for _, label, setting in CANDS]
    lines += ["", "## 목차", ""]
    lines += [f"- [{d['company']} — {d['title']}](#{d['rec_idx']})" for d in data]
    for d in data:
        lines += ["", f'<a id="{d["rec_idx"]}"></a>', f"## {d['company']} — {d['title']} ({d['rec_idx']})", "",
                  f"- 사람인 공고 페이지: {d['posting']}", f"- 추출한 본문(relay): {d['relay']}"]
        for im in d["images"]:
            lines.append(f"- 이미지 [{im['file']}](../images/{im['file']}) ({im['size']}) · 원본 주소: {im['url']}")
        for t in d["texts"]:
            lines += ["", f"### {t['label']} — {t['meta']} · [원문 파일]({t['file']})", "", "~~~text",
                      t["text"].rstrip(), "~~~"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    data = collect()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(OUT_DIR, "ocr_texts.html"), "w", encoding="utf-8") as f:
        f.write(HTML.replace("__DATA__", blob))
    write_md(data, os.path.join(OUT_DIR, "ocr_texts.md"))
    print("out/ocr_texts.html, out/ocr_texts.md 작성:", len(data), "건")


if __name__ == "__main__":
    main()
