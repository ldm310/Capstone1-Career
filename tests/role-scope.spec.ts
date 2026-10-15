import { test, expect } from "@playwright/test";
import { classifyJobRole, normalizeRole } from "../lib/roles";
import { mutation } from "../lib/server/schema";

test("classify explicit data/backend openings without relabelling unrelated jobs", () => {
  for (const name of [
    "Data Analyst",
    "Data Scientist",
    "데이터 엔지니어",
    "Data Platform Engineer",
  ])
    expect(classifyJobRole(name)).toBe("data");
  for (const name of [
    "Backend Engineer",
    "Back-end Developer",
    "백엔드 개발자",
    "서버 개발자",
  ])
    expect(classifyJobRole(name)).toBe("backend");
  for (const name of [
    "Machine Learning Engineer",
    "AI Engineer",
    "Frontend Developer",
    "Software Engineer",
    "Database Administrator",
  ])
    expect(classifyJobRole(name)).toBeNull();
  expect(normalizeRole("ax")).toBe("data");
  expect(normalizeRole("ml")).toBe("data");
  expect(normalizeRole("backend")).toBe("backend");
  const preference = {
    action: "preferences",
    role: "backend",
    region: "",
    experience: "",
    hours: 5,
    targetDate: "",
  };
  expect(mutation.safeParse(preference).success).toBe(true);
  expect(mutation.safeParse({ ...preference, role: "ml" }).success).toBe(false);
});

test("two roles persist through real guest preferences and drive preparation", async ({
  page,
  request,
}) => {
  expect((await request.get("/api/jobs?role=ax")).status()).toBe(400);
  await page.goto("/my-skills");
  const role = page.getByRole("combobox", { name: "목표 직무", exact: true });
  await expect(role.locator("option")).toHaveText(["데이터", "백엔드"]);
  await role.selectOption("backend");
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/api/career") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "준비 조건 저장" }).click();
  expect((await saved).ok()).toBe(true);
  await page.reload();
  await expect(role).toHaveValue("backend");
  await page.goto("/preparation");
  await expect(page.locator(".learning-path")).toContainText("REST API");
  await expect(page.locator(".learning-path")).not.toContainText("MCP");
  await page.goto("/jobs");
  await expect(page.getByLabel("공고 직무").locator("option")).toHaveText([
    "모든 직무",
    "데이터",
    "백엔드",
  ]);
});
