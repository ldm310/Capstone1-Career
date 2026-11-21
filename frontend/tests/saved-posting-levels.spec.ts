import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import examples from "@/mock/reviewed-keyword-examples.json";
import { demoAccount } from "@/lib/server/demo-account";
import AxeBuilder from "@axe-core/playwright";

test("RDS demo LVs are session-scoped, persistent and drawn to scale", async ({
  page,
  playwright,
}) => {
  test.skip(
    process.env.RUN_RDS_LV_TESTS !== "1",
    "Explicit opt-in to existing RDS fixture",
  );
  test.setTimeout(120000);
  const base = "http://127.0.0.1:3000";
  const path = `/api/jobs/my-levels?jobId=study-demo-backend&version=${examples.version}`;
  const anonymous = await playwright.request.newContext({ baseURL: base });
  expect((await anonymous.get(path)).status()).toBe(401);
  expect(
    (
      await page.request.post("/api/account", {
        headers: { origin: base },
        data: {
          action: "login",
          email: demoAccount.email,
          password: demoAccount.password,
        },
      })
    ).ok(),
  ).toBe(true);
  const firstResponse = await page.request.get(path);
  expect(firstResponse.status()).toBe(200);
  expect(firstResponse.headers()["cache-control"]).toContain("no-store");
  const first = await firstResponse.json();
  expect(first.source).toBe("RDS");
  expect(first.levels.length).toBeGreaterThan(5);
  expect(
    first.levels.every(
      (row: { evaluationKind: string }) => row.evaluationKind === "DEMO",
    ),
  ).toBe(true);
  expect(
    first.sources.map((source: { kind: string }) => source.kind).sort(),
  ).toEqual(["GITHUB", "PDF"]);
  const second = await (
    await page.request.get(
      path.replace("study-demo-backend", "study-demo-data"),
    )
  ).json();
  expect(first.levels.map((row: { score: number }) => row.score)).not.toEqual(
    second.levels.map((row: { score: number }) => row.score),
  );
  expect((await (await page.request.get(path)).json()).levels).toEqual(
    first.levels,
  );
  expect(
    (
      await (
        await page.request.get(path.replace(examples.version, "old-taxonomy"))
      ).json()
    ).levels,
  ).toEqual([]);
  const liveKeywordsResponse = await page.request.get(
    "/api/jobs/keywords?jobId=be:4562",
  );
  expect(liveKeywordsResponse.status()).toBe(200);
  const liveKeywords = await liveKeywordsResponse.json();
  expect(liveKeywords.keywords.length).toBeGreaterThan(0);
  const liveLevels = await (
    await page.request.get(
      `/api/jobs/my-levels?jobId=be:4562&version=${liveKeywords.version}`,
    )
  ).json();
  expect(
    liveLevels.levels.map((row: { keywordId: string }) => row.keywordId).sort(),
  ).toEqual(liveKeywords.keywords.map((row: { id: string }) => row.id).sort());

  const other = await playwright.request.newContext({ baseURL: base });
  expect(
    (
      await other.post("/api/account", {
        headers: { origin: base },
        data: {
          action: "register",
          email: `lv-test-${randomUUID()}@example.test`,
          password: randomUUID(),
          name: "격리 검증",
        },
      })
    ).ok(),
  ).toBe(true);
  const isolated = await (await other.get(path + "&userId=demo-user")).json();
  expect(isolated.levels).toEqual([]);
  expect(isolated.sources).toEqual([]);

  await page.goto(
    "/jobs?job=study-demo-backend&demo=low#job-personal-comparison",
  );
  const radar = page.getByTestId("saved-level-radar");
  await expect(radar).toBeVisible();
  await expect(page.locator(".saved-level-radar")).toContainText(
    "경쟁자 평균 (더미)",
  );
  const geometry = await radar.evaluate((svg) => {
    const points = (kind: string) =>
      svg
        .querySelector(`polygon[data-series="${kind}"]`)!
        .getAttribute("points")!
        .split(" ")
        .map((pair) => pair.split(",").map(Number));
    return { mine: points("mine"), reference: points("reference") };
  });
  // This posting fixture has exactly six categorized requirements, not all ten axes.
  expect(geometry.mine).toHaveLength(6);
  expect(geometry.reference).toHaveLength(6);
  const programming = first.levels.filter((row: { categoryCodes: string[] }) =>
    row.categoryCodes.includes("L"),
  );
  const average =
    programming.reduce(
      (sum: number, row: { score: number }) => sum + row.score,
      0,
    ) / programming.length;
  expect(200 - geometry.mine[0][1]).toBeCloseTo((average / 100) * 118, 6);
  expect(geometry.mine[0][0]).toBeCloseTo(260, 6);
  await expect(radar).toHaveAttribute(
    "aria-label",
    new RegExp(`내 LV ${average.toFixed(1)}`),
  );
  await page.locator(".saved-level-radar").screenshot({
    path: "work/saved-lv-radar.png",
    style:
      ".site-header, .skip-link, nextjs-portal { visibility: hidden !important; }",
  });
  await page.reload();
  await expect(page.getByTestId("saved-level-radar")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.locator(".saved-level-radar").screenshot({
    path: "work/saved-lv-radar-mobile.png",
    style:
      ".site-header, .skip-link, nextjs-portal { visibility: hidden !important; }",
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await anonymous.dispose();
  await other.dispose();
});
