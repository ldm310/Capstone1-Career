/* Career 다이어그램 화살표 — edges([...])로 카드 id 사이에 직각 화살표를 그린다.
 * 각 항목: {from, to, kind?, fromSide?, toSide?, fromAt?, toAt?, midX?, midY?, via?, label?, labelSeg?, labelAt?,
 *          labelDx?, labelDy?, labelSize?, labelColor?, both?, noArrow?, gap?}
 * kind: flow(데이터 흐름) | loop(재판정·반복) | ref(참고·피드백, 점선) | risk(위험 분기) | no(아니오·보류) | llm
 * side: right | left | top | bottom (생략하면 위치로 자동 선택), at: 변 위 비율 0~1 (기본 0.5) 또는 "align"(상대편 점에 맞춰 곧게)
 * via: [{x}|{y}|{x,y}|{xOf:id, side, offset}|{yOf:id, side, offset}] 순서대로 지나는 직각 경유점
 * 그린 뒤 window.__edgeIssues 에 겹침 검사 결과, window.__edgesDone = true 를 남긴다.
 */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const KINDS = {
    flow: { color: "#8fa89a", width: 2.5, text: "#5f7c6d" },
    loop: { color: "#1f6f4a", width: 3, text: "#1a5c40" },
    ref: { color: "#8fa89a", width: 2.5, dash: "7 6", text: "#5f7c6d" },
    risk: { color: "#c0782d", width: 2.5, text: "#a35f1c" },
    no: { color: "#b4502f", width: 2.5, text: "#9c3f22" },
    llm: { color: "#4b6fae", width: 2.5, text: "#2d4f86" },
  };
  const BG = "#f4f6f4";

  function rel(el, page) {
    const r = el.getBoundingClientRect();
    const p = page.getBoundingClientRect();
    return { x: r.left - p.left, y: r.top - p.top, w: r.width, h: r.height };
  }
  function anchor(r, side, at) {
    const t = at == null ? 0.5 : at;
    if (side === "right") return [r.x + r.w, r.y + r.h * t];
    if (side === "left") return [r.x, r.y + r.h * t];
    if (side === "top") return [r.x + r.w * t, r.y];
    return [r.x + r.w * t, r.y + r.h];
  }
  function autoSides(a, b) {
    if (b.x >= a.x + a.w - 2) return ["right", "left"];
    if (b.x + b.w <= a.x + 2) return ["left", "right"];
    return b.y + b.h / 2 > a.y + a.h / 2 ? ["bottom", "top"] : ["top", "bottom"];
  }
  const horiz = (s) => s === "left" || s === "right";

  function sideCoord(id, side, offset, page) {
    const el = document.getElementById(id);
    if (!el) throw new Error("via 기준 id 없음: " + id);
    const r = rel(el, page);
    const o = offset || 0;
    if (side === "left") return r.x + o;
    if (side === "right") return r.x + r.w + o;
    if (side === "top") return r.y + o;
    if (side === "bottom") return r.y + r.h + o;
    if (side === "centerX") return r.x + r.w / 2 + o;
    return r.y + r.h / 2 + o;
  }

  function route(p0, fs, p3, ts, e, page) {
    if (e.via && e.via.length) {
      const pts = [p0];
      let cur = p0;
      for (const v of e.via) {
        let x = v.x,
          y = v.y;
        if (v.xOf) x = sideCoord(v.xOf, v.side || "right", v.offset, page);
        if (v.yOf) y = sideCoord(v.yOf, v.side || "bottom", v.offset, page);
        const next = [x != null ? x : cur[0], y != null ? y : cur[1]];
        if (next[0] !== cur[0] && next[1] !== cur[1]) pts.push([next[0], cur[1]]);
        pts.push(next);
        cur = next;
      }
      if (horiz(ts)) {
        if (cur[1] !== p3[1]) pts.push([cur[0], p3[1]]);
      } else if (cur[0] !== p3[0]) pts.push([p3[0], cur[1]]);
      pts.push(p3);
      return pts;
    }
    const H0 = horiz(fs),
      H3 = horiz(ts);
    if (H0 && H3) {
      let mx = e.midX;
      if (mx == null && fs === ts)
        mx = fs === "right" ? Math.max(p0[0], p3[0]) + 28 : Math.min(p0[0], p3[0]) - 28;
      if (mx == null) {
        if (Math.abs(p0[1] - p3[1]) < 0.5) return [p0, p3];
        mx = (p0[0] + p3[0]) / 2;
      }
      return [p0, [mx, p0[1]], [mx, p3[1]], p3];
    }
    if (!H0 && !H3) {
      let my = e.midY;
      if (my == null && fs === ts)
        my = fs === "bottom" ? Math.max(p0[1], p3[1]) + 28 : Math.min(p0[1], p3[1]) - 28;
      if (my == null) {
        if (Math.abs(p0[0] - p3[0]) < 0.5) return [p0, p3];
        my = (p0[1] + p3[1]) / 2;
      }
      return [p0, [p0[0], my], [p3[0], my], p3];
    }
    if (H0 && !H3) return [p0, [p3[0], p0[1]], p3];
    return [p0, [p0[0], p3[1]], p3];
  }

  function dedupe(pts) {
    const out = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      const p = out[out.length - 1];
      if (Math.abs(p[0] - pts[i][0]) > 0.3 || Math.abs(p[1] - pts[i][1]) > 0.3) out.push(pts[i]);
    }
    return out;
  }
  function pullBack(a, b, gap) {
    const dx = b[0] - a[0],
      dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    const g = Math.min(gap, len / 2);
    return [b[0] - (dx / len) * g, b[1] - (dy / len) * g];
  }
  function segHitsRect(a, b, r, inset) {
    const x0 = r.x + inset,
      x1 = r.x + r.w - inset,
      y0 = r.y + inset,
      y1 = r.y + r.h - inset;
    const sx0 = Math.min(a[0], b[0]),
      sx1 = Math.max(a[0], b[0]),
      sy0 = Math.min(a[1], b[1]),
      sy1 = Math.max(a[1], b[1]);
    return sx1 > x0 && sx0 < x1 && sy1 > y0 && sy0 < y1;
  }
  function overlap(a, b, pad) {
    return (
      a.x < b.x + b.w - pad && a.x + a.w > b.x + pad && a.y < b.y + b.h - pad && a.y + a.h > b.y + pad
    );
  }

  function draw(list) {
    const page = document.querySelector(".page");
    const old = page.querySelector("svg.edges");
    if (old) old.remove();
    const W = page.scrollWidth,
      H = page.scrollHeight;
    const svg = document.createElementNS(NS, "svg");
    svg.classList.add("edges");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    const defs = document.createElementNS(NS, "defs");
    svg.appendChild(defs);
    page.appendChild(svg);
    const made = {};
    function marker(kind, color) {
      const id = "m-" + kind;
      if (made[id]) return id;
      const m = document.createElementNS(NS, "marker");
      m.setAttribute("id", id);
      m.setAttribute("viewBox", "0 0 12 12");
      m.setAttribute("refX", "11");
      m.setAttribute("refY", "6");
      m.setAttribute("markerWidth", "12");
      m.setAttribute("markerHeight", "12");
      m.setAttribute("markerUnits", "userSpaceOnUse");
      m.setAttribute("orient", "auto-start-reverse");
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", "M0,1 L12,6 L0,11 z");
      p.setAttribute("fill", color);
      m.appendChild(p);
      defs.appendChild(m);
      made[id] = true;
      return id;
    }

    const boxes = Array.from(page.querySelectorAll(".card, [data-box]"));
    const issues = [];
    const labels = [];
    list.forEach((e, i) => {
      const a = document.getElementById(e.from),
        b = document.getElementById(e.to);
      if (!a || !b) {
        issues.push({ type: "missing-id", edge: i, from: e.from, to: e.to });
        return;
      }
      const ra = rel(a, page),
        rb = rel(b, page);
      let fs = e.fromSide,
        ts = e.toSide;
      if (!fs || !ts) {
        const s = autoSides(ra, rb);
        fs = fs || s[0];
        ts = ts || s[1];
      }
      const p0 = anchor(ra, fs, typeof e.fromAt === "number" ? e.fromAt : null),
        p3 = anchor(rb, ts, typeof e.toAt === "number" ? e.toAt : null);
      // fromAt/toAt: "align" → 상대편 점과 같은 x(세로 변) 또는 y(가로 변)에 맞춰 곧게 (변 범위 안으로 제한)
      const clamp = (v, lo, hi) => Math.max(lo + 8, Math.min(hi - 8, v));
      if (e.fromAt === "align") {
        if (horiz(fs)) p0[1] = clamp(p3[1], ra.y, ra.y + ra.h);
        else p0[0] = clamp(p3[0], ra.x, ra.x + ra.w);
      }
      if (e.toAt === "align") {
        if (horiz(ts)) p3[1] = clamp(p0[1], rb.y, rb.y + rb.h);
        else p3[0] = clamp(p0[0], rb.x, rb.x + rb.w);
      }
      // 거의 일직선이면 작은 꺾임 대신 곧은 선으로 맞춘다 (출발 변 안에서만)
      if (!e.via && e.fromAt == null && e.midX == null && e.midY == null) {
        if (horiz(fs) && horiz(ts) && fs !== ts && Math.abs(p0[1] - p3[1]) < 18 && p3[1] > ra.y + 6 && p3[1] < ra.y + ra.h - 6)
          p0[1] = p3[1];
        if (!horiz(fs) && !horiz(ts) && fs !== ts && Math.abs(p0[0] - p3[0]) < 18 && p3[0] > ra.x + 6 && p3[0] < ra.x + ra.w - 6)
          p0[0] = p3[0];
      }
      const pts = dedupe(route(p0, fs, p3, ts, e, page));
      const kind = KINDS[e.kind] ? e.kind : "flow";
      const k = KINDS[kind];
      const gap = e.gap == null ? 2 : e.gap;
      const drawn = pts.slice();
      if (!e.noArrow) drawn[drawn.length - 1] = pullBack(drawn[drawn.length - 2], drawn[drawn.length - 1], gap);
      if (e.both) drawn[0] = pullBack(drawn[1], drawn[0], gap);
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", "M" + drawn.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L"));
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", k.color);
      path.setAttribute("stroke-width", k.width);
      path.setAttribute("stroke-linejoin", "round");
      if (k.dash) path.setAttribute("stroke-dasharray", k.dash);
      if (!e.noArrow) path.setAttribute("marker-end", "url(#" + marker(kind, k.color) + ")");
      if (e.both) path.setAttribute("marker-start", "url(#" + marker(kind, k.color) + ")");
      svg.appendChild(path);

      for (const box of boxes) {
        if (box === a || box === b || box.contains(a) || box.contains(b) || a.contains(box) || b.contains(box))
          continue;
        const r = rel(box, page);
        for (let s = 0; s < pts.length - 1; s++) {
          if (segHitsRect(pts[s], pts[s + 1], r, 3)) {
            issues.push({ type: "edge-crosses-box", edge: i, from: e.from, to: e.to, box: box.id || box.className });
            break;
          }
        }
      }
      if (e.label) labels.push({ e, i, pts, k });
    });

    for (const { e, i, pts, k } of labels) {
      let s = e.labelSeg;
      if (s == null) {
        let best = -1;
        s = 0;
        for (let j = 0; j < pts.length - 1; j++) {
          const len = Math.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]);
          if (len > best) {
            best = len;
            s = j;
          }
        }
      }
      s = Math.max(0, Math.min(s, pts.length - 2));
      const p = pts[s],
        q = pts[s + 1];
      const t = e.labelAt == null ? 0.5 : e.labelAt;
      const x = p[0] + (q[0] - p[0]) * t + (e.labelDx || 0);
      const y = p[1] + (q[1] - p[1]) * t + (e.labelDy || 0);
      const size = e.labelSize || 13.5;
      const lines = String(e.label).split("\n");
      const g = document.createElementNS(NS, "g");
      const text = document.createElementNS(NS, "text");
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("font-size", size);
      text.setAttribute("fill", e.labelColor || k.text);
      lines.forEach((line, li) => {
        const span = document.createElementNS(NS, "tspan");
        span.setAttribute("x", x);
        span.setAttribute("y", y + (li - (lines.length - 1) / 2) * size * 1.3 + size * 0.36);
        span.textContent = line;
        text.appendChild(span);
      });
      g.appendChild(text);
      svg.appendChild(g);
      const bb = text.getBBox();
      const rect = document.createElementNS(NS, "rect");
      rect.setAttribute("x", bb.x - 6);
      rect.setAttribute("y", bb.y - 3);
      rect.setAttribute("width", bb.width + 12);
      rect.setAttribute("height", bb.height + 6);
      rect.setAttribute("rx", 4);
      rect.setAttribute("fill", e.labelBg || BG);
      g.insertBefore(rect, text);
      const lr = { x: bb.x - 6, y: bb.y - 3, w: bb.width + 12, h: bb.height + 6 };
      for (const box of boxes) {
        if (overlap(lr, rel(box, page), 1))
          issues.push({ type: "label-overlaps-box", edge: i, label: e.label, box: box.id || box.className });
      }
    }
    window.__edgeIssues = issues;
    window.__edgesDone = true;
  }

  window.edges = function (list) {
    const run = function () {
      try {
        draw(list);
      } catch (err) {
        window.__edgeIssues = [{ type: "error", message: String(err && err.message ? err.message : err) }];
        window.__edgesDone = true;
      }
    };
    const ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    ready.then(function () {
      requestAnimationFrame(function () {
        requestAnimationFrame(run);
      });
    });
  };
})();
