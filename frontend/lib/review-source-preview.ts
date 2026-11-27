// Render stored source HTML in an isolated, script-free iframe. Keep text,
// tables and HTTPS images; discard executable markup, styles and navigation.
export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
const escape = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
export function reviewSourceDocument(html: string): string {
  if (typeof DOMParser === "undefined") return "";
  const document = new DOMParser().parseFromString(html, "text/html");
  const allowed = new Set(
    "p div span section article main header footer h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table thead tbody tfoot tr th td strong b em i u s small sub sup blockquote pre code br hr img figure figcaption".split(
      " ",
    ),
  );
  const blocked = new Set(
    "script style iframe frame frameset object embed svg math form input button textarea select option link meta base template noscript audio video source".split(
      " ",
    ),
  );
  function render(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return escape(node.textContent || "");
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const element = node as Element,
      tag = element.tagName.toLowerCase();
    if (blocked.has(tag)) return "";
    const children = () => Array.from(node.childNodes).map(render).join("");
    if (!allowed.has(tag)) return children();
    if (tag === "img") {
      const src = safeSourceUrl(element.getAttribute("src") || "");
      return src
        ? '<img src="' +
            escape(src) +
            '" alt="' +
            escape(element.getAttribute("alt") || "공고 원문 이미지") +
            '" referrerpolicy="no-referrer" loading="lazy">'
        : "";
    }
    if (tag === "br" || tag === "hr") return "<" + tag + ">";
    const attrs = ["colspan", "rowspan"]
      .filter((key) => /^[1-9]\d{0,2}$/.test(element.getAttribute(key) || ""))
      .map((key) => " " + key + '="' + element.getAttribute(key) + '"')
      .join("");
    return "<" + tag + attrs + ">" + children() + "</" + tag + ">";
  }
  return (
    '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src https:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><style>body{margin:0;padding:18px;color:#263b50;background:white;font:14px/1.75 system-ui,\"Malgun Gothic\",sans-serif;overflow-wrap:anywhere}*{box-sizing:border-box;max-width:100%}img{display:block;height:auto;margin:12px auto}table{width:100%;border-collapse:collapse}td,th{border:1px solid #dbe3ec;padding:8px}pre{white-space:pre-wrap}h1,h2,h3,h4{line-height:1.5}p{margin:8px 0}</style></head><body>' +
    Array.from(document.body.childNodes).map(render).join("") +
    "</body></html>"
  );
}
