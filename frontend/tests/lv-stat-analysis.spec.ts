import {
  expect,
  request,
  test,
  type APIRequestContext,
  type APIResponse,
} from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { demoAccount } from "@/lib/server/demo-account";

// GitHub 계정 LV 분석 요청 API(/api/lv-stat/analysis)를 dev 서버로 시험한다. 로그인은 다른 e2e 시험처럼
// /api/account 가입·로그인이다. 분석 작업자는 돌지 않는다(요청은 queued로 남고 GitHub에 가지 않는다).
// 작업자가 쓰는 파일(끝난 요청·분석 결과)은 이 시험이 작업자 대신 둔다. 그래서 dev 서버와 같은 환경 변수
// (CAREER_DATA_DIR·CAREER_PROFILE_NAMESPACE)로 돌린다. CI=1이면 playwright가 이 환경으로 서버를 새로 띄운다.

const route = "/api/lv-stat/analysis";
const urlHelp = "GitHub 계정 주소를 넣어 주세요. 예: https://github.com/아이디";
const valid = { url: "https://github.com/synthetic-user" };
const noStore = "private, no-store";
const uuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
// lib/server/lv-stat.ts의 lvDataDir, notices.ts의 profileNamespace와 같은 기준(CONTRACT.md의 폴더).
const namespace = process.env.CAREER_PROFILE_NAMESPACE || "local-review";
const dataDir = path.join(
  process.env.CAREER_DATA_DIR || path.join(process.cwd(), ".career-data"),
  "lv-stat",
);
const jobsDir = path.join(dataDir, "jobs");
// CONTRACT: sha256(namespace + ":" + subjectId)의 16진수 앞 32자.
const profileKey = (subjectId: string) =>
  createHash("sha256")
    .update(`${namespace}:${subjectId}`)
    .digest("hex")
    .slice(0, 32);

// 응답 하나를 비교하기 쉬운 모양으로. JSON이 아니면(없는 route의 404 화면 등) 본문 대신 표시만 둔다.
async function answer(response: APIResponse) {
  return {
    status: response.status(),
    cacheControl: response.headers()["cache-control"],
    body: await response.json().catch(() => "(JSON 아님)"),
  };
}
const refused = (status: number, error: unknown) => ({
  status,
  cacheControl: noStore,
  body: { error },
});
const found = (body: unknown) => ({ status: 200, cacheControl: noStore, body });
const nothing = found({ job: null, profile: null });

test.describe("analysis API", () => {
  let contexts: APIRequestContext[] = [];
  // 시험이 만들거나 둔 파일. 시험마다 지운다(남은 queued 요청이 다음 실행의 전체 대기 상한 20건을 채우지 않게).
  let files: string[] = [];

  test.afterEach(async () => {
    await Promise.all(contexts.map((context) => context.dispose()));
    await Promise.all(files.map((file) => rm(file, { force: true })));
    contexts = [];
    files = [];
  });

  // 쿠키를 따로 가진 방문자 하나.
  async function visitor(baseURL: string) {
    const api = await request.newContext({ baseURL });
    contexts.push(api);
    return api;
  }

  // 새 회원으로 가입한 방문자와 그 회원 id.
  async function signUp(baseURL: string) {
    const api = await visitor(baseURL);
    const response = await api.post("/api/account", {
      headers: { Origin: baseURL },
      data: {
        action: "register",
        email: `lv-analysis-${randomUUID()}@example.test`,
        password: "Career-test-2026!",
        name: "분석 시험",
      },
    });
    expect(response.ok()).toBe(true);
    return { api, id: (await response.json()).user.id as string };
  }

  // 분석 요청. origin이 없으면 Origin 머리글 없이 보낸다. 202로 만든 요청 파일은 시험 뒤에 지운다.
  async function post(api: APIRequestContext, data: unknown, origin?: string) {
    const response = await api.post(route, {
      headers: origin === undefined ? {} : { Origin: origin },
      data,
    });
    const id = (await response.json().catch(() => null))?.job?.id;
    if (typeof id === "string" && uuid.test(id))
      files.push(path.join(jobsDir, `${id}.json`));
    return response;
  }

  // 작업자처럼 파일을 둔다.
  async function plant(dir: string, name: string, text: string, mode = 0o600) {
    await mkdir(dir, { recursive: true, mode: 0o700 });
    const file = path.join(dir, name);
    files.push(file);
    await writeFile(file, text, { mode });
  }

  // 작업자가 끝낸 요청(CONTRACT.md 모양). 끝난 요청은 작업자가 다시 집지 않는다.
  async function finishedJob(subjectId: string) {
    const job = {
      id: randomUUID(),
      namespace,
      subjectId,
      login: "synthetic-user",
      input: "https://github.com/synthetic-user",
      status: "done",
      createdAt: "2026-11-28T00:00:00.000Z",
      stage: "끝",
      progress: { done: 1, total: 1 },
      startedAt: "2026-11-28T00:00:01.000Z",
      finishedAt: "2026-11-28T00:05:00.000Z",
      profileKey: profileKey(subjectId),
    };
    await plant(jobsDir, `${job.id}.json`, JSON.stringify(job));
    return job;
  }

  // 작업자가 쓴 분석 결과(CONTRACT.md 모양, 합성 값).
  async function analyzed(subjectId: string) {
    const profile = {
      schema: "lv-stat-profile/1",
      method: "lv-stat-s2-20261127",
      labels: ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"],
      namespace,
      subjectId,
      login: "synthetic-user",
      jobId: randomUUID(),
      analyzedAt: "2026-11-28T00:05:00.000Z",
      repos: { found: 2, analyzed: 1, failed: 1, notes: ["합성 메모"] },
      categories: {
        L: {
          name: "프로그래밍 활용",
          lv: 2.5,
          unknown: 0,
          languages: { Java: 2.5, Python: 1.0 },
          best: "Java",
        },
        O: { name: "운영 배포", lv: 1.0, unknown: 0 },
        B: { name: "백엔드 개발", lv: 2.0, unknown: 1 },
        E: { name: "데이터 엔지니어", lv: 0, unknown: 0 },
        D: { name: "데이터베이스", lv: 1.5, unknown: 0 },
        F: { name: "프론트엔드 앱", lv: null, unknown: 2 },
        A: { name: "AI 기술", lv: 0, unknown: 0 },
      },
    };
    await plant(
      path.join(dataDir, "profiles"),
      `${profileKey(subjectId)}.json`,
      JSON.stringify(profile),
    );
    return profile;
  }

  test("signed-out visitors and guests get 401 for POST and GET", async ({
    baseURL,
  }) => {
    const api = await visitor(baseURL!);
    for (const guest of [false, true]) {
      if (guest)
        expect(
          (
            await api.post("/api/guest", { headers: { Origin: baseURL! } })
          ).ok(),
        ).toBe(true);
      expect(await answer(await post(api, valid, baseURL))).toEqual(
        refused(401, expect.any(String)),
      );
      expect(await answer(await api.get(route))).toEqual(
        refused(401, expect.any(String)),
      );
    }
  });

  test("a POST from another site or without an origin is refused with 403", async ({
    baseURL,
  }) => {
    const { api } = await signUp(baseURL!);
    for (const origin of ["https://untrusted.example", "null", undefined])
      expect(await answer(await post(api, valid, origin))).toEqual(
        refused(403, "요청 출처를 확인할 수 없습니다."),
      );
    expect(await answer(await api.get(route))).toEqual(nothing);
  });

  test("an address that is not a GitHub account gets 400 with an example", async ({
    baseURL,
  }) => {
    const { api } = await signUp(baseURL!);
    for (const data of [
      { url: "https://gitlab.com/synthetic-user" },
      {},
      { url: 42 },
      "not json",
    ])
      expect(await answer(await post(api, data, baseURL))).toEqual(
        refused(400, urlHelp),
      );
    expect(await answer(await api.get(route))).toEqual(nothing);
  });

  test("a member's request is queued with the trimmed address, GET returns it, and a second request is 409", async ({
    baseURL,
  }) => {
    const { api, id } = await signUp(baseURL!);
    const posted = await answer(
      await post(
        api,
        { url: "  https://github.com/Synthetic-User/sample-repo/  " },
        baseURL,
      ),
    );
    expect(posted).toEqual({
      status: 202,
      cacheControl: noStore,
      body: {
        job: {
          id: expect.stringMatching(uuid),
          namespace,
          subjectId: id,
          login: "Synthetic-User",
          input: "https://github.com/Synthetic-User/sample-repo/",
          status: "queued",
          createdAt: expect.any(String),
        },
      },
    });
    const { job } = posted.body;
    expect(await answer(await api.get(route))).toEqual(
      found({ job, profile: null }),
    );
    expect(await answer(await post(api, valid, baseURL))).toEqual(
      refused(409, "이미 분석 중이에요. 끝나면 다시 시도해 주세요."),
    );
    expect(await answer(await api.get(route))).toEqual(
      found({ job, profile: null }),
    );
  });

  test("another member's GET has no one else's job, even when asked by id", async ({
    baseURL,
  }) => {
    const first = await signUp(baseURL!);
    const own = (await answer(await post(first.api, valid, baseURL))).body.job;
    expect(own).toMatchObject({ subjectId: first.id, status: "queued" });
    const second = await signUp(baseURL!);
    for (const query of [
      "",
      `?subjectId=${first.id}&userId=${first.id}&jobId=${own.id}`,
    ])
      expect(await answer(await second.api.get(route + query))).toEqual(
        nothing,
      );
    const theirs = await answer(await post(second.api, valid, baseURL));
    expect(theirs.status).toBe(202);
    expect(theirs.body.job.subjectId).toBe(second.id);
    expect(await answer(await first.api.get(route))).toEqual(
      found({ job: own, profile: null }),
    );
  });

  test("the seventh POST within 15 minutes is 429, counted per member", async ({
    baseURL,
  }) => {
    const { api } = await signUp(baseURL!);
    for (let attempt = 1; attempt <= 6; attempt++)
      expect((await post(api, { url: "not a url" }, baseURL)).status()).toBe(
        400,
      );
    expect(await answer(await post(api, valid, baseURL))).toEqual(
      refused(429, "요청이 많습니다. 15분 후 다시 시도해 주세요."),
    );
    expect(await answer(await api.get(route))).toEqual(nothing);
    const other = await signUp(baseURL!);
    expect((await post(other.api, valid, baseURL)).status()).toBe(202);
  });

  test("GET returns the finished job and the profile the worker wrote", async ({
    baseURL,
  }) => {
    const { api, id } = await signUp(baseURL!);
    const job = await finishedJob(id);
    const profile = await analyzed(id);
    expect(await answer(await api.get(route))).toEqual(found({ job, profile }));
  });

  test("the shared demo account can neither request nor read an analysis", async ({
    baseURL,
  }) => {
    const demo = await visitor(baseURL!);
    const login = await demo.post("/api/account", {
      headers: { Origin: baseURL! },
      data: {
        action: "login",
        email: demoAccount.email,
        password: demoAccount.password,
      },
    });
    expect(login.ok()).toBe(true);
    const demoId = (await login.json()).user.id as string;
    await finishedJob(demoId);
    await analyzed(demoId);
    expect(await answer(await demo.get(route))).toEqual(nothing);
    const before = (await readdir(jobsDir)).sort();
    expect(await answer(await post(demo, valid, baseURL))).toEqual(
      refused(403, "데모 계정은 GitHub 분석을 할 수 없어요."),
    );
    expect((await readdir(jobsDir)).sort()).toEqual(before);
  });

  test("a job file the server cannot read gives 500 without the file path", async ({
    baseURL,
  }) => {
    test.skip(process.getuid?.() === 0, "root는 권한 없는 파일도 읽는다");
    const { api } = await signUp(baseURL!);
    await plant(jobsDir, `${randomUUID()}.json`, "{}", 0o000);
    for (const response of [
      await post(api, valid, baseURL),
      await api.get(route),
    ]) {
      const { status, cacheControl, body } = await answer(response);
      expect({ status, cacheControl }).toEqual({
        status: 500,
        cacheControl: noStore,
      });
      expect(body.error).toMatch(/[가-힣]/);
      expect(body.error).not.toContain(jobsDir);
      expect(body.error).not.toContain("EACCES");
    }
  });
});
