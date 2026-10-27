import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
test("account: reviews and tasks persist; points and ranking are gone", async ({
  request,
  baseURL,
}) => {
  const headers = { Origin: baseURL! };
  const signup = await request.post("/api/account", {
    headers,
    data: {
      action: "register",
      name: "성장 검증",
      email: `growth-test-${randomUUID()}@example.com`,
      password: "Growth-test-2026!",
    },
  });
  expect(signup.ok()).toBeTruthy();
  const upload = await request.post("/api/documents", {
    headers,
    multipart: {
      file: {
        name: "notes.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(
          "# Notes\nDocker 프로젝트와 postgres 데이터베이스 구현 기록입니다.",
        ),
      },
      source: "notion",
    },
  });
  expect(upload.ok()).toBeTruthy();
  const denied = await request.post("/api/documents", {
    headers,
    multipart: {
      file: {
        name: "notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Docker project implementation notes"),
      },
    },
  });
  expect(denied.ok()).toBeFalsy();
  let data = await (await request.get("/api/growth")).json();
  expect(Object.keys(data)).toEqual(["growth"]);
  expect(Object.keys(data.growth).sort()).toEqual(["reviews", "tasks"]);
  expect(
    data.growth.reviews.some(
      (r: { skill: string }) => r.skill === "PostgreSQL",
    ),
  ).toBeTruthy();
  for (let i = 0; i < 2; i++) {
    expect(
      (
        await request.post("/api/growth", {
          headers,
          data: { action: "start", skill: "Docker", level: 1 },
        })
      ).ok(),
    ).toBeTruthy();
  }
  data = await (await request.get("/api/growth")).json();
  expect(data.growth.tasks).toHaveLength(1);
  await request.post("/api/growth", {
    headers,
    data: {
      action: "submit",
      id: data.growth.tasks[0].id,
      evidence: "old project",
      explanation: "기존 프로젝트의 자료를 추가로 제출합니다.",
    },
  });
  data = await (await request.get("/api/growth")).json();
  expect(data.growth.tasks[0].status).toBe("needs_evidence");
  expect(data.growth.tasks[0]).not.toHaveProperty("reward");
  expect(
    (
      await request.post("/api/growth", {
        headers,
        data: { action: "award", points: 999 },
      })
    ).ok(),
  ).toBeFalsy();
  expect(
    (
      await request.post("/api/growth", {
        headers,
        data: { action: "settings", nickname: "공개", publicRanking: true },
      })
    ).ok(),
  ).toBeFalsy();
});
