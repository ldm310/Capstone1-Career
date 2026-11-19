import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { test, expect } from "@playwright/test";
import { GET as jobs } from "@/app/api/jobs/route";
import { GET as categories } from "@/app/api/skill-categories/route";

let server: Server;
let previousUrl: string | undefined;
let requests: string[] = [];
let failed = false;
const catalog = {
  version: "flat-10-infra-review-20261119",
  categories: [{ code: "O", sentenceCount: 1127 }],
  otherSentences: 880,
};

test.beforeAll(async () => {
  previousUrl = process.env.BACKEND_URL;
  server = createServer((request, response) => {
    requests.push(request.url!);
    response.setHeader("Content-Type", "application/json");
    if (failed) {
      response.writeHead(500).end("{}");
      return;
    }
    if (request.url === "/api/skill-categories") {
      response.end(JSON.stringify(catalog));
      return;
    }
    if (request.url === "/api/postings/9001") {
      response.end(
        JSON.stringify({
          postingId: 9001,
          companyName: "계약 검증 회사",
          title: "백엔드 개발자",
          site: "saramin",
          sitePostingNo: "123",
          siteJobCategory: "백엔드",
          careerCondition: "무관",
          minYears: null,
          employmentType: "정규직",
          kind: "글",
          status: "진행",
          deadline: null,
          collectedAt: "2026-11-19T00:00:00Z",
          lastCheckedAt: "2026-11-19T00:00:00Z",
          analysis: null,
        }),
      );
      return;
    }
    response.writeHead(404).end("{}");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  process.env.BACKEND_URL = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(async () => {
  if (previousUrl === undefined) delete process.env.BACKEND_URL;
  else process.env.BACKEND_URL = previousUrl;
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});
test.beforeEach(() => {
  requests = [];
  failed = false;
});

test("backend detail bypasses the 200-item list and public feeds", async () => {
  const result = await jobs(
    new Request("http://localhost/api/jobs?id=be:9001"),
  );
  expect(result.status).toBe(200);
  expect((await result.json()).jobs[0]).toMatchObject({
    id: "be:9001",
    company: "계약 검증 회사",
  });
  expect(requests).toEqual(["/api/postings/9001"]);
});
test("invalid IDs, missing data and backend failures remain distinct", async () => {
  expect(
    (await jobs(new Request("http://localhost/api/jobs?id=be:0"))).status,
  ).toBe(400);
  expect(requests).toEqual([]);
  expect(
    (
      await (
        await jobs(new Request("http://localhost/api/jobs?id=be:9999"))
      ).json()
    ).jobs,
  ).toEqual([]);
  failed = true;
  expect(
    (await jobs(new Request("http://localhost/api/jobs?id=be:9001"))).status,
  ).toBe(502);
});
test("category proxy preserves saved counts and does not fabricate fallback data", async () => {
  const response = await categories();
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual(catalog);
  failed = true;
  expect((await categories()).status).toBe(502);
  const configured = process.env.BACKEND_URL;
  try {
    delete process.env.BACKEND_URL;
    expect((await categories()).status).toBe(503);
  } finally {
    process.env.BACKEND_URL = configured;
  }
});
