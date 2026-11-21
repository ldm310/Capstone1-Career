import { test, expect } from "@playwright/test";
import { GET } from "@/app/api/jobs/keywords/route";
import { currentFindings } from "@/lib/workspace-selectors";
import { emptyWorkspace } from "@/types/workspace";

test("different uploaded resumes with the same filename both contribute evidence", () => {
  const finding = {
    id: "finding",
    skill: "SQL",
    type: "career" as const,
    title: "resume.pdf",
    quote: "experience",
    url: "/documents/example",
    detectedAt: "2026-11-21",
  };
  const state = {
    ...emptyWorkspace,
    runs: [
      {
        id: "one",
        sourceId: "document:one",
        title: "resume.pdf",
        at: "2026-11-21",
        findings: [{ ...finding, id: "one" }],
      },
      {
        id: "two",
        sourceId: "document:two",
        title: "resume.pdf",
        at: "2026-11-21",
        findings: [{ ...finding, id: "two" }],
      },
    ],
  };
  expect(currentFindings(state).map((item) => item.id)).toEqual(["one", "two"]);
});

test("saved posting classifications keep reviewed, countable requirements and leave LV pending", async () => {
  const previous = process.env.BACKEND_URL;
  const originalFetch = globalThis.fetch;
  process.env.BACKEND_URL = "http://backend.test";
  const item = (
    itemId: number,
    status: string,
    categoryCodes: string[],
    excludedFromCounts = false,
    needsReview = false,
  ) => ({
    itemId,
    text: `Reviewed requirement ${itemId}`,
    sourceCategory: "필수",
    assignment: { status, categoryCodes, excludedFromCounts, needsReview },
  });
  let requested = "";
  globalThis.fetch = async (input) => {
    requested = String(input);
    return Response.json({
      version: "saved-v1",
      recruitUnits: [
        {
          items: [
            item(1, "CLASSIFIED", ["B", "D"]),
            item(2, "EXCLUDED", [], true),
            item(3, "CLASSIFIED", ["X"]),
            item(4, "UNCLASSIFIED", []),
            item(5, "CLASSIFIED", ["B"], false, true),
          ],
        },
      ],
    });
  };
  try {
    const response = await GET(
      new Request("http://local/api/jobs/keywords?jobId=be:4375"),
    );
    const data = await response.json();
    expect(requested).toBe(
      "http://backend.test/api/postings/4375/skill-categories",
    );
    expect(data.source).toBe("SAVED_REVIEW");
    expect(data.keywords).toEqual([
      {
        id: "1",
        text: "Reviewed requirement 1",
        requirementType: "필수",
        categoryCodes: ["B", "D"],
        level: null,
      },
    ]);
    expect(data.levelScoringEnabled).toBe(false);
  } finally {
    globalThis.fetch = originalFetch;
    if (previous === undefined) delete process.env.BACKEND_URL;
    else process.env.BACKEND_URL = previous;
  }
});

test("classification lookup failures remain failures; examples are explicitly labelled and unscored", async () => {
  const previous = process.env.BACKEND_URL;
  delete process.env.BACKEND_URL;
  try {
    expect(
      (await GET(new Request("http://local/api/jobs/keywords?jobId=be:4375")))
        .status,
    ).toBe(503);
    expect(
      (await GET(new Request("http://local/api/jobs/keywords"))).status,
    ).toBe(400);
    const data = await (
      await GET(
        new Request("http://local/api/jobs/keywords?jobId=study-demo-backend"),
      )
    ).json();
    expect(data.source).toBe("EXAMPLE");
    expect(data.keywords.length).toBe(6);
    expect(
      data.keywords.every(
        (keyword: { level: number | null }) => keyword.level === null,
      ),
    ).toBe(true);
  } finally {
    if (previous !== undefined) process.env.BACKEND_URL = previous;
  }
});

test("job detail displays the saved requirement text, not a technology-name LV", async ({
  page,
}) => {
  await page.goto("/jobs?job=study-demo-backend&demo=low");
  await expect(page.locator(".job-keyword-levels li")).toHaveCount(6);
  await expect(page.locator(".job-keyword-levels li").first()).toContainText(
    "산정 전",
  );
  await expect(
    page.locator(".job-keyword-levels li strong").first(),
  ).not.toHaveText("SQL");
  await expect(page.locator(".job-keyword-levels")).toContainText(
    "저장된 분류 문장",
  );
});
