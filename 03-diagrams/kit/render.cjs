// 사용법: node kit/render.cjs <input.html> <output.png>
// .page 요소를 2배 해상도 PNG로 저장하고, 겹침·넘침·작은 글씨·폰트 문제를 JSON으로 출력한다.
const path = require("path");
const { createRequire } = require("module");
const req = createRequire("/Users/idongmin/Desktop/capstone1-career/package.json");
const { chromium } = req("@playwright/test");

(async () => {
  const [htmlArg, pngArg] = process.argv.slice(2);
  if (!htmlArg || !pngArg) {
    console.error("usage: node render.cjs <input.html> <output.png>");
    process.exit(2);
  }
  const html = path.resolve(htmlArg);
  const png = path.resolve(pngArg);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1320, height: 1000 }, deviceScaleFactor: 2 });
  const logs = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") logs.push(m.type() + ": " + m.text());
  });
  page.on("pageerror", (e) => logs.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => logs.push("requestfailed: " + r.url()));
  await page.goto("file://" + html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  const edgesOk = await page
    .waitForFunction(() => window.__edgesDone === true, null, { timeout: 8000 })
    .then(() => true)
    .catch(() => false);
  if (!edgesOk) logs.push("warn: edges()가 호출되지 않았거나 끝나지 않음 (화살표 없음)");

  const report = await page.evaluate(() => {
    const pageEl = document.querySelector(".page");
    if (!pageEl) return { error: ".page 요소 없음" };
    const P = pageEl.getBoundingClientRect();
    const rel = (el) => {
      const r = el.getBoundingClientRect();
      return { x: r.left - P.left, y: r.top - P.top, w: r.width, h: r.height };
    };
    const name = (el) => el.id || (el.className && el.className.baseVal === undefined ? el.className : el.tagName);
    const boxes = Array.from(pageEl.querySelectorAll(".card, [data-box]"));
    const overlaps = [];
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i],
          b = boxes[j];
        if (a.contains(b) || b.contains(a)) continue;
        const ra = rel(a),
          rb = rel(b);
        const ix = Math.min(ra.x + ra.w, rb.x + rb.w) - Math.max(ra.x, rb.x);
        const iy = Math.min(ra.y + ra.h, rb.y + rb.h) - Math.max(ra.y, rb.y);
        if (ix > 2 && iy > 2) overlaps.push([name(a), name(b)]);
      }
    const overflow = [];
    pageEl.querySelectorAll("*").forEach((el) => {
      const cs = getComputedStyle(el);
      if (el.closest("svg")) return;
      if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== "visible" && el.clientWidth > 0)
        overflow.push({ el: name(el), kind: "x" });
      if (el.scrollHeight > el.clientHeight + 2 && cs.overflowY !== "visible" && el.clientHeight > 0)
        overflow.push({ el: name(el), kind: "y" });
    });
    const outside = [];
    boxes.forEach((el) => {
      const r = rel(el);
      if (r.x < -1 || r.y < -1 || r.x + r.w > P.width + 1 || r.y + r.h > P.height + 1)
        outside.push(name(el));
    });
    // 카드 밖으로 삐져나온 글자 (고정 크기 카드에서 내용이 넘친 경우)
    const spill = [];
    boxes.forEach((box) => {
      const br = box.getBoundingClientRect();
      box.querySelectorAll("*").forEach((child) => {
        if (child.closest("svg")) return;
        const cr = child.getBoundingClientRect();
        if (cr.width === 0 || cr.height === 0) return;
        if (cr.right > br.right + 1 || cr.bottom > br.bottom + 1 || cr.left < br.left - 1)
          spill.push({ box: name(box), child: child.tagName + (child.className ? "." + child.className : "") });
      });
    });
    const small = new Set();
    pageEl.querySelectorAll("*").forEach((el) => {
      if (el.closest("svg")) return;
      const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
      if (!hasText) return;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 12) small.add(el.tagName + "." + el.className + " " + fs + "px");
    });
    return {
      cssWidth: Math.round(P.width),
      cssHeight: Math.round(P.height),
      fontOk: document.fonts.check('700 18px "Pretendard"'),
      boxOverlaps: overlaps,
      overflow: overflow.slice(0, 30),
      spill: spill.slice(0, 30),
      outsidePage: outside,
      smallText: Array.from(small).slice(0, 20),
      edgeIssues: window.__edgeIssues || [],
    };
  });
  const el = await page.$(".page");
  if (el) await el.screenshot({ path: png });
  await browser.close();
  const problems =
    (report.boxOverlaps || []).length +
    (report.overflow || []).length +
    (report.spill || []).length +
    (report.outsidePage || []).length +
    (report.edgeIssues || []).length +
    (report.fontOk ? 0 : 1) +
    logs.length;
  console.log(JSON.stringify({ png, problems, report, logs }, null, 2));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
