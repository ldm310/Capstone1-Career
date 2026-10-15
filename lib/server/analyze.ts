import { randomUUID } from "node:crypto";
import type { Finding, JobAnalysis } from "@/types/workspace";
import { patterns } from "@/lib/skill-patterns";
export function extract(
  text: string,
  title: string,
  url: string,
  type: Finding["type"],
): Finding[] {
  const lines = text.split("\n");
  return Object.entries(patterns).flatMap(([skill, regex]) => {
    const line = lines.findIndex((x) => regex.test(x));
    return line < 0
      ? []
      : [
          {
            id: randomUUID(),
            skill,
            type,
            title,
            quote: lines
              .slice(Math.max(0, line - 1), line + 2)
              .join("\n")
              .slice(0, 650),
            url:
              url +
              (url.includes("github.com/") || url.startsWith("/documents/")
                ? `#L${line + 1}`
                : ""),
            detectedAt: new Date().toISOString(),
          },
        ];
  });
}
async function getJson(url: string, headers: Record<string, string> = {}) {
  const res = await fetch(url, {
    headers,
    redirect: "error",
    signal: AbortSignal.timeout(12000),
    cache: "no-store",
  });
  if (!res.ok)
    throw new Error(
      `원본 서비스 조회 실패 (${res.status}). URL·공유 권한·호출 한도를 확인하세요.`,
    );
  return res.json();
}
export async function github(input: string) {
  const url = new URL(input);
  const parts = url.pathname.split("/").filter(Boolean);
  if (
    url.protocol !== "https:" ||
    url.hostname !== "github.com" ||
    parts.length !== 2 ||
    !parts.every((x) => /^[\w.-]+$/.test(x))
  )
    throw new Error(
      "공개 GitHub 저장소 주소를 입력하세요. 예: https://github.com/owner/repo",
    );
  const [owner, repo] = parts;
  const base = `https://api.github.com/repos/${owner}/${repo}`;
  const headers = {
    Accept: "application/vnd.github+json",
    "User-Agent": "Career",
  };
  const info = await getJson(base, headers);
  if (info.private) throw new Error("공개 저장소만 지원합니다.");
  const tree = await getJson(
    `${base}/git/trees/${encodeURIComponent(info.default_branch)}?recursive=1`,
    headers,
  );
  const files = (
    tree.tree as { path: string; type: string; size: number; sha: string }[]
  )
    .filter(
      (x) =>
        x.type === "blob" &&
        x.size < 100000 &&
        !/node_modules|vendor|lock|\.env|secret|credential/i.test(x.path) &&
        /\.(py|ts|tsx|js|java|kt|gradle|xml|json|ya?ml|md|sql|txt)$|Dockerfile$/i.test(
          x.path,
        ),
    )
    .sort(
      (a, b) =>
        Number(/Dockerfile|requirements|package.json/.test(b.path)) -
        Number(/Dockerfile|requirements|package.json/.test(a.path)),
    )
    .slice(0, 20);
  const findings: Finding[] = [];
  for (const file of files) {
    const blob = await getJson(`${base}/git/blobs/${file.sha}`, headers);
    const content = Buffer.from(blob.content, "base64").toString("utf8");
    findings.push(
      ...extract(
        content,
        file.path,
        `https://github.com/${owner}/${repo}/blob/${tree.sha}/${file.path.split("/").map(encodeURIComponent).join("/")}`,
        /\.md$|package.json|requirements/.test(file.path)
          ? "learning"
          : "implementation",
      ),
    );
  }
  return {
    findings: findings.slice(0, 120),
    title: `${owner}/${repo} · 최대 20개 파일 검사${tree.truncated ? " · 일부 트리만 조회" : ""}`,
  };
}
export async function notion(input: string, token: string) {
  if (!token)
    throw new Error(
      "Notion 연결 토큰이 필요합니다. 또는 내보낸 Markdown 파일을 분석하세요.",
    );
  const url = new URL(input);
  if (
    url.protocol !== "https:" ||
    !/(^|\.)(notion\.so|notion\.site)$/.test(url.hostname)
  )
    throw new Error("Notion 페이지 주소를 입력하세요.");
  const id = url.pathname.replaceAll("-", "").match(/[a-f0-9]{32}$/i)?.[0];
  if (!id) throw new Error("페이지 ID를 찾을 수 없습니다.");
  const findings: Finding[] = [];
  const queue = [id];
  let count = 0;
  while (queue.length && count < 12) {
    const current = queue.shift()!;
    const result = await getJson(
      `https://api.notion.com/v1/blocks/${current}/children?page_size=100`,
      { Authorization: `Bearer ${token}`, "Notion-Version": "2022-06-28" },
    );
    count++;
    for (const block of result.results) {
      const text = (block[block.type]?.rich_text || [])
        .map((r: { plain_text: string }) => r.plain_text)
        .join("");
      findings.push(
        ...extract(
          text,
          "Notion 학습 기록",
          `${url.origin}${url.pathname}#${block.id.replaceAll("-", "")}`,
          "learning",
        ),
      );
      if (block.has_children) queue.push(block.id);
    }
  }
  return {
    title: "Notion · 최대 12개 블록 그룹 / 각 100개 블록 검사",
    findings: findings.slice(0, 120),
  };
}
const plain = (s: string) =>
  s
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&");
export async function jobAnalysis(
  urlString: string,
  textInput: string,
  company: string,
  title: string,
): Promise<JobAnalysis> {
  let text = textInput;
  const sections: { title: string; text: string }[] = [];
  if (urlString) {
    const url = new URL(urlString);
    const parts = url.pathname.split("/").filter(Boolean);
    if (
      url.protocol !== "https:" ||
      url.hostname !== "jobs.lever.co" ||
      parts.length !== 2 ||
      !parts.every((x) => /^[\w-]+$/.test(x))
    )
      throw new Error(
        "자동 수집은 Lever 공고 URL을 지원합니다. 다른 공고는 URL을 비우고 본문을 붙여넣으세요.",
      );
    const data = await getJson(
      `https://api.lever.co/v0/postings/${parts[0]}/${parts[1]}?mode=json`,
    );
    title = data.text || title;
    company = company || parts[0];
    for (const list of data.lists || [])
      sections.push({ title: list.text, text: plain(list.content) });
    text = [
      data.descriptionPlain,
      ...sections.map((x) => `${x.title}\n${x.text}`),
      data.additionalPlain,
    ]
      .filter(Boolean)
      .join("\n");
  } else {
    let heading = "분류 미확인";
    for (const line of text.split("\n")) {
      if (
        /^(자격.?요건|필수|우대|preferred|requirements|qualifications|nice.to.have)/i.test(
          line.trim(),
        )
      )
        heading = line.trim();
      sections.push({ title: heading, text: line });
    }
  }
  if (text.trim().length < 30)
    throw new Error("공고 본문을 30자 이상 입력하세요.");
  const required = new Set<string>(),
    preferred = new Set<string>();
  for (const section of sections) {
    const destination = /우대|preferred|nice.to.have|bonus/i.test(section.title)
      ? preferred
      : /필수|자격|requirement|qualification|must/i.test(section.title)
        ? required
        : null;
    if (destination)
      for (const [skill, regex] of Object.entries(patterns))
        if (regex.test(section.text)) destination.add(skill);
  }
  const unknown = Object.entries(patterns)
    .filter(
      ([skill, re]) =>
        re.test(text) && !required.has(skill) && !preferred.has(skill),
    )
    .map(([s]) => s);
  return {
    id: randomUUID(),
    company: company || "직접 입력 공고",
    title: title || "채용공고",
    url: urlString,
    required: [...required],
    preferred: [...preferred],
    unknown,
    text: text.slice(0, 60000),
  };
}
