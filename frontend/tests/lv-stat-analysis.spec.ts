import {
  expect,
  request,
  test,
  type APIRequestContext,
  type APIResponse,
  type Locator,
  type Page,
} from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { demoAccount } from "@/lib/server/demo-account";
import examples from "@/mock/reviewed-keyword-examples.json";
import type { LvJob, LvProfile } from "@/types/lv-stat";

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

// 작업자가 쓴 분석 결과(CONTRACT.md 모양, 합성 값). 화면 시험도 같은 값을 쓴다. jobId는 그 결과를 낸 요청이다.
function syntheticProfile(
  subjectId: string,
  jobId: string = randomUUID(),
): LvProfile {
  return {
    schema: "lv-stat-profile/1",
    method: "lv-stat-s2-20261127",
    labels: ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"],
    namespace,
    subjectId,
    login: "synthetic-user",
    jobId,
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
}

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
    const profile = syntheticProfile(subjectId);
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

// 분석 화면(/analysis의 새 칸)과 공고 상세의 레이더 차트. API는 page.route로 흉내 낸다(서버의 작업자·GitHub에
// 가지 않는다). 진행 중에 5초마다 읽는 것은 page.clock으로 시간을 넘겨 본다. 시계는 페이지가 다 뜬 뒤에 멈춘다
// (playwright 안내대로, 뜨는 동안의 타이머는 그대로 돈다).
test.describe("analysis screen", () => {
  const title = "GitHub 계정으로 공고별 LV 보기";
  const guide = "분석이 끝나면 공고 상세의 레이더 차트에 공고마다 LV가 나와요.";
  const labelLine = "2단계 규칙 · LLM 보충 끔 · 제안 기준 · 본인 확인 안 됨";
  const address = "https://github.com/synthetic-user";
  const loaded = new Date("2026-11-28T09:00:00+09:00");
  const paused = new Date("2026-11-28T09:10:00+09:00");
  const summary = [
    "프로그래밍 활용 LV 2.5",
    "운영 배포 LV 1.0",
    "백엔드 개발 LV 2.0 · 모름 1개",
    "데이터 엔지니어 LV 0.0",
    "데이터베이스 LV 1.5",
    "프론트엔드 앱 판정 불가 · 모름 2개",
    "AI 기술 LV 0.0",
  ];
  type Reply = { status: number; json: unknown };
  // GET 답으로 "lost"를 두면 답하지 않고 연결을 끊는다(fetch가 실패한다).
  type Answer = Reply | "lost";

  // 화면 시험의 요청 id. 끝난 요청의 결과(profile.jobId)는 이 id다(작업자가 쓰는 그대로).
  const screenJobId = "00000000-0000-4000-8000-000000000012";
  function job(fields: Partial<LvJob>): LvJob {
    return {
      id: screenJobId,
      namespace,
      subjectId: "screen-member",
      login: "synthetic-user",
      input: address,
      status: "queued",
      createdAt: "2026-11-28T00:00:00.000Z",
      ...fields,
    };
  }
  const reading = (
    fields: Partial<LvJob>,
    profile: LvProfile | null = null,
  ) => ({
    status: 200,
    json: { job: job(fields), profile },
  });

  // 기존 분석 흐름(AnalysisFlow)과 머리글이 묻는 계정. 화면 칸 자체는 /api/lv-stat/analysis의 401로 로그인을 안다.
  async function account(page: Page, member: boolean) {
    await page.route("**/api/account", (route) =>
      route.fulfill({
        json: {
          user: member ? { id: "screen-member", name: "화면 시험" } : null,
          guest: false,
        },
      }),
    );
  }

  // /api/lv-stat/analysis 흉내. GET·POST마다 지금 정해 둔 답을 주고, 읽은 횟수(끊은 GET 포함)와 보낸 본문을 센다.
  async function analysisApi(page: Page) {
    const calls = { get: 0, posts: [] as unknown[] };
    let get: Answer = { status: 200, json: { job: null, profile: null } };
    let post: Reply = { status: 202, json: { job: job({}) } };
    await page.route("**/api/lv-stat/analysis", (route) => {
      const sent = route.request();
      if (sent.method() === "POST") {
        calls.posts.push(sent.postDataJSON());
        return route.fulfill(post);
      }
      calls.get++;
      return get === "lost"
        ? route.abort("connectionrefused")
        : route.fulfill(get);
    });
    return {
      calls,
      answerGet: (reply: Answer) => void (get = reply),
      answerPost: (reply: Reply) => void (post = reply),
    };
  }

  // 시간을 넘긴 뒤 읽기 요청이 생겼다면 route까지 닿을 틈을 준다(없어야 하는 요청을 셀 때).
  async function settle(page: Page) {
    await page.waitForTimeout(500);
  }

  test("signed-out visitors see the login prompt instead of the form, above the existing flow", async ({
    page,
  }) => {
    await account(page, false);
    const api = await analysisApi(page);
    api.answerGet({ status: 401, json: { error: "로그인이 필요합니다." } });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    await expect(block.getByRole("heading", { level: 2 })).toHaveText(title);
    await expect(block).toContainText(guide);
    await expect(block.getByText("로그인이 필요합니다.")).toBeVisible();
    await expect(
      block.getByRole("link", { name: "로그인, 회원가입" }),
    ).toHaveAttribute("href", "/sign-in?next=%2Fanalysis");
    await expect(
      block.getByPlaceholder("https://github.com/아이디"),
    ).toHaveCount(0);
    await expect(
      block.getByRole("button", { name: "분석 시작", exact: true }),
    ).toHaveCount(0);
    expect(
      await block.evaluate(
        (section) =>
          section.compareDocumentPosition(
            document.querySelector(".analysis-flow")!,
          ) & Node.DOCUMENT_POSITION_FOLLOWING,
      ),
    ).toBeTruthy();
    expect(api.calls.posts).toEqual([]);
  });

  test("the block is not drawn before the first read answers, nor when the API answers 404 (switch off)", async ({
    page,
  }) => {
    // 스테이징 스위치가 꺼진 서버(운영)는 분석 API가 404다. 첫 GET 답을 잡아 두고, 답하기 전에도 404로 답한 뒤에도
    // 칸이 없는지 본다(운영에서 칸이 잠깐 보였다 사라지지 않게).
    await account(page, true);
    let answer: (reply: Reply) => void = () => {};
    const held = new Promise<Reply>((resolve) => (answer = resolve));
    let gets = 0;
    await page.route("**/api/lv-stat/analysis", async (route) => {
      gets++;
      await route.fulfill(await held);
    });
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    await expect(page.locator(".analysis-flow")).toBeVisible();
    await expect.poll(() => gets).toBeGreaterThan(0);
    await expect(page.locator(".github-lv-analysis")).toHaveCount(0);
    await expect(page.getByText(title)).toHaveCount(0);
    answer({ status: 404, json: { error: "GitHub 분석을 쓸 수 없어요." } });
    await settle(page);
    await expect(page.locator(".github-lv-analysis")).toHaveCount(0);
    await expect(page.getByText("GitHub 분석을 쓸 수 없어요.")).toHaveCount(0);
    await page.clock.pauseAt(paused);
    const first = gets;
    await page.clock.runFor(30000);
    await settle(page);
    expect(gets).toBe(first);
    await expect(page.locator(".analysis-flow")).toBeVisible();
  });

  test("a member starts an analysis, sees the stage every 5 seconds, then the summary, and reading stops", async ({
    page,
  }) => {
    await account(page, true);
    const api = await analysisApi(page);
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    const start = block.getByRole("button", { name: "분석 시작", exact: true });
    const status = block.getByRole("status");
    await expect(block).toContainText(guide);
    await block.getByPlaceholder("https://github.com/아이디").fill(address);
    await expect(start).toBeEnabled();
    await page.clock.pauseAt(paused);
    const first = api.calls.get;
    expect(first).toBeGreaterThan(0);

    await start.click();
    await expect(status).toHaveText("대기");
    expect(api.calls.posts).toEqual([{ url: address }]);
    await expect(start).toBeDisabled();
    await expect(block.getByRole("listitem")).toHaveCount(0);

    api.answerGet(
      reading({
        status: "running",
        stage: "레포 받기",
        progress: { done: 2, total: 5 },
      }),
    );
    await page.clock.runFor(4900);
    await settle(page);
    expect(api.calls.get).toBe(first);
    await page.clock.runFor(100);
    await expect(status).toHaveText("레포 받기 (2/5)");
    expect(api.calls.get).toBe(first + 1);

    api.answerGet(
      reading(
        {
          status: "done",
          stage: "끝",
          progress: { done: 5, total: 5 },
          profileKey: profileKey("screen-member"),
        },
        syntheticProfile("screen-member", screenJobId),
      ),
    );
    await page.clock.runFor(5000);
    await expect(block.getByRole("listitem")).toHaveText(summary);
    await expect(block).toContainText(labelLine);
    await expect(status).toHaveText("");
    expect(api.calls.get).toBe(first + 2);
    await expect(start).toBeEnabled();

    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(first + 2);
  });

  // 끝난 요청인데 결과가 그 요청의 것이 아니면(다른 분석의 결과이거나 없음) 아직 끝나지 않은 것으로 보고 같은 간격으로 더 읽는다.
  async function startedThenDone(page: Page, stale: LvProfile | null) {
    await account(page, true);
    const api = await analysisApi(page);
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    const start = block.getByRole("button", { name: "분석 시작", exact: true });
    await block.getByPlaceholder("https://github.com/아이디").fill(address);
    await expect(start).toBeEnabled();
    await page.clock.pauseAt(paused);
    const first = api.calls.get;
    api.answerGet(reading({ status: "done", stage: "끝" }, stale));
    await start.click();
    await expect(block.getByRole("status")).toHaveText("대기");
    // 5초마다 한 번 읽는다. 다음 차례를 잡을 틈을 준 뒤 시간을 넘긴다.
    const readAgain = async (count: number) => {
      await page.clock.runFor(5000);
      await expect.poll(() => api.calls.get).toBe(first + count);
      await settle(page);
    };
    return { api, block, first, readAgain };
  }

  test("a done job whose profile arrives on a later read shows that summary and stops reading", async ({
    page,
  }) => {
    const { api, block, first, readAgain } = await startedThenDone(
      page,
      syntheticProfile("screen-member"),
    );
    await readAgain(1);
    await expect(block.getByRole("listitem")).toHaveCount(0); // 다른 분석의 결과는 보이지 않는다
    api.answerGet(
      reading(
        { status: "done", stage: "끝" },
        syntheticProfile("screen-member", screenJobId),
      ),
    );
    await readAgain(2);
    await expect(block.getByRole("listitem")).toHaveText(summary);
    await expect(block.getByRole("alert")).toHaveCount(0);
    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(first + 2);
  });

  test("a done job whose profile never arrives is read 3 more times, then the block says the result could not be loaded", async ({
    page,
  }) => {
    const { api, block, first, readAgain } = await startedThenDone(page, null);
    for (let count = 1; count <= 4; count++) {
      await readAgain(count);
      if (count < 4) await expect(block.getByRole("alert")).toHaveCount(0);
    }
    await expect(block.getByRole("alert")).toHaveText(
      "분석 결과를 불러오지 못했어요.",
    );
    await expect(block.getByRole("listitem")).toHaveCount(0);
    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(first + 4);
  });

  // 결과를 기다리며 다시 읽는 동안 GET이 401·404·그 밖의 오류로 답하거나 연결이 끊기면, POST 401처럼 요청과 결과를 비우고
  // 기다림을 끝낸다(같은 답이 계속 오면 5초마다 끝없이 읽지 않게). 그 뒤 시간을 5초씩 1분 넘기며 읽은 수를 센다.
  const waitEnders: {
    answer: Answer;
    what: string;
    then: string;
    check: (page: Page, block: Locator) => Promise<void>;
  }[] = [
    {
      answer: { status: 401, json: { error: "로그인이 필요합니다." } },
      what: "a 401",
      then: "shows the login prompt",
      check: async (_page, block) => {
        await expect(block.getByText("로그인이 필요합니다.")).toBeVisible();
        await expect(
          block.getByRole("link", { name: "로그인, 회원가입" }),
        ).toBeVisible();
        await expect(
          block.getByPlaceholder("https://github.com/아이디"),
        ).toHaveCount(0);
      },
    },
    {
      answer: { status: 404, json: { error: "GitHub 분석을 쓸 수 없어요." } },
      what: "a 404 (switch off)",
      then: "is not drawn",
      check: async (page) => {
        await expect(page.locator(".github-lv-analysis")).toHaveCount(0);
        await expect(page.locator(".analysis-flow")).toBeVisible();
      },
    },
    {
      answer: { status: 500, json: { error: "합성 서버 오류" } },
      what: "a 500",
      then: "shows the API's error",
      check: async (_page, block) => {
        await expect(block.getByRole("alert")).toHaveText("합성 서버 오류");
      },
    },
    {
      answer: "lost",
      what: "a lost connection",
      then: "asks to check the connection",
      check: async (_page, block) => {
        await expect(block.getByRole("alert")).toHaveText(
          "연결을 확인해 주세요.",
        );
      },
    },
  ];
  for (const { answer, what, then, check } of waitEnders) {
    test(`while a done job waits for its result, ${what} ends the wait: the block ${then} and reading stops`, async ({
      page,
    }) => {
      // done인데 결과는 다른 분석의 것이다: 기다리며 다시 읽는 중. 기다림이 끝나도 그 결과는 보이지 않는다.
      const { api, block, first, readAgain } = await startedThenDone(
        page,
        syntheticProfile("screen-member"),
      );
      await readAgain(1);
      api.answerGet(answer);
      await readAgain(2);
      for (let step = 0; step < 12; step++) {
        await page.clock.runFor(5000);
        await settle(page);
      }
      expect(api.calls.get).toBe(first + 2);
      await check(page, block);
      await expect(block.getByRole("listitem")).toHaveCount(0);
    });
  }

  test("a finished analysis shows the summary when the page opens, without reading again", async ({
    page,
  }) => {
    await account(page, true);
    const api = await analysisApi(page);
    api.answerGet(
      reading(
        { status: "done", stage: "끝", progress: { done: 1, total: 1 } },
        syntheticProfile("screen-member", screenJobId),
      ),
    );
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    await expect(block.getByRole("listitem")).toHaveText(summary);
    await expect(block).toContainText(labelLine);
    // 아무 공개 계정이나 넣을 수 있으므로 어느 계정을 언제(한국 시각) 분석했는지, 레포 수와 메모(시간 상한 등)를 그대로 보인다.
    await expect(block).toContainText(
      "synthetic-user · 2026. 11. 28. 09:05 분석",
    );
    await expect(block).toContainText("레포 2개 찾음 · 분석 1개 · 실패 1개");
    await expect(block.getByText("합성 메모", { exact: true })).toBeVisible();
    await page.clock.pauseAt(paused);
    const first = api.calls.get;
    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(first);
  });

  test("a failed analysis shows the worker's error as written, stops reading, and 다시 시도 asks again with the same address", async ({
    page,
  }) => {
    await account(page, true);
    const api = await analysisApi(page);
    const error = "GitHub 호출 한도에 걸렸습니다(12분 뒤 다시 시도)";
    api.answerGet(
      reading({
        status: "failed",
        stage: "실패",
        error,
        input: "https://github.com/Synthetic-User/",
      }),
    );
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    await expect(block.getByRole("alert")).toHaveText(error);
    const retry = block.getByRole("button", { name: "다시 시도", exact: true });
    await expect(retry).toBeVisible();
    await page.clock.pauseAt(paused);
    const first = api.calls.get;
    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(first);

    await retry.click();
    await expect(block.getByRole("status")).toHaveText("대기");
    expect(api.calls.posts).toEqual([
      { url: "https://github.com/Synthetic-User/" },
    ]);
    await expect(block.getByRole("alert")).toHaveCount(0);
    await expect(retry).toHaveCount(0);
  });

  test("a refused request shows the API's error as written, and a 401 turns the form into the login prompt", async ({
    page,
  }) => {
    await account(page, true);
    const api = await analysisApi(page);
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    const input = block.getByPlaceholder("https://github.com/아이디");
    const start = block.getByRole("button", { name: "분석 시작", exact: true });
    await input.fill(address);
    for (const reply of [
      { status: 403, error: "데모 계정은 GitHub 분석을 할 수 없어요." },
      { status: 409, error: "이미 분석 중이에요. 끝나면 다시 시도해 주세요." },
    ]) {
      api.answerPost({ status: reply.status, json: { error: reply.error } });
      await start.click();
      await expect(block.getByRole("alert")).toHaveText(reply.error);
      await expect(start).toBeEnabled();
      await expect(input).toHaveValue(address);
      await expect(block.getByRole("status")).toHaveText("");
    }
    api.answerPost({ status: 401, json: { error: "로그인이 필요합니다." } });
    await start.click();
    await expect(block.getByText("로그인이 필요합니다.")).toBeVisible();
    await expect(
      block.getByRole("link", { name: "로그인, 회원가입" }),
    ).toBeVisible();
    await expect(input).toHaveCount(0);
    expect(api.calls.posts).toHaveLength(3);
  });

  // analysis-flow.spec.ts의 휴대폰 폭·axe 시험은 그 앞(홈 메뉴 글)에서 이미 실패해 /analysis까지 가지 않는다
  // (ad977ff에서도 같음). 그래서 새 칸이 가장 넓을 때(요약·실패 글·오류 글)를 여기서 본다.
  test("the block fits phone widths and passes axe with the summary, the failure and an error", async ({
    page,
  }) => {
    await account(page, true);
    const api = await analysisApi(page);
    api.answerGet(
      reading(
        {
          status: "failed",
          stage: "실패",
          error: "GitHub 호출 한도에 걸렸습니다(12분 뒤 다시 시도)",
        },
        syntheticProfile("screen-member"),
      ),
    );
    api.answerPost({
      status: 429,
      json: { error: "요청이 많습니다. 15분 후 다시 시도해 주세요." },
    });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    await block.getByPlaceholder("https://github.com/아이디").fill(address);
    await block.getByRole("button", { name: "분석 시작", exact: true }).click();
    await expect(block.getByRole("alert")).toHaveCount(2);
    await expect(block.getByRole("listitem")).toHaveText(summary);
    for (const width of [768, 390, 320]) {
      await page.setViewportSize({ width, height: 960 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await block.screenshot({ path: "work/github-lv-analysis-mobile.png" });
    expect(
      (
        await new AxeBuilder({ page })
          .include(".github-lv-analysis")
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
  });

  test("leaving the page stops reading", async ({ page }) => {
    await account(page, true);
    const api = await analysisApi(page);
    await page.clock.install({ time: loaded });
    await page.goto("/analysis");
    const block = page.getByRole("region", { name: title });
    await block.getByPlaceholder("https://github.com/아이디").fill(address);
    const start = block.getByRole("button", { name: "분석 시작", exact: true });
    await expect(start).toBeEnabled();
    await page.clock.pauseAt(paused);
    await start.click();
    await expect(block.getByRole("status")).toHaveText("대기");
    api.answerGet(
      reading({
        status: "running",
        stage: "색인",
        progress: { done: 1, total: 3 },
      }),
    );
    await page.clock.runFor(5000);
    await expect(block.getByRole("status")).toHaveText("색인 (1/3)");
    await page
      .getByRole("navigation", { name: "주 메뉴" })
      .getByRole("link", { name: "채용 공고" })
      .click();
    await expect(page).toHaveURL(/\/jobs$/);
    await expect(block).toHaveCount(0);
    const left = api.calls.get;
    await page.clock.runFor(30000);
    await settle(page);
    expect(api.calls.get).toBe(left);
  });

  test("a posting scored from the analysis shows the labels line, no dummy mark or blue line, and puts each row only on its usedCodes axes", async ({
    page,
  }) => {
    await account(page, true);
    await page.route("**/api/career", (route) =>
      route.fulfill({ json: { workspace: { runs: [], documents: [] } } }),
    );
    await page.route("**/api/growth", (route) =>
      route.fulfill({ json: { growth: { reviews: [], tasks: [] } } }),
    );
    // 합성 공고 문장. 백엔드+프론트 문장은 프론트 LV가 없어(판정 불가) 백엔드로만 점수를 냈고(usedCodes),
    // 프론트만 있는 문장은 점수가 없어 행이 없다. 그래서 프론트 축은 없어야 한다.
    const keywords = [
      {
        id: "synthetic-l",
        text: "합성 문장 하나",
        codes: ["L"],
        used: ["L"],
        score: 50,
      },
      {
        id: "synthetic-bf",
        text: "합성 문장 둘",
        codes: ["B", "F"],
        used: ["B"],
        score: 40,
      },
      {
        id: "synthetic-d",
        text: "합성 문장 셋",
        codes: ["D"],
        used: ["D"],
        score: 30,
      },
      {
        id: "synthetic-o",
        text: "합성 문장 넷",
        codes: ["O"],
        used: ["O"],
        score: 20,
      },
      {
        id: "synthetic-f",
        text: "합성 문장 다섯",
        codes: ["F"],
        used: [],
        score: null,
      },
    ];
    await page.route("**/api/jobs/keywords?**", (route) =>
      route.fulfill({
        json: {
          source: "SAVED_REVIEW",
          version: examples.version,
          keywords: keywords.map((keyword) => ({
            id: keyword.id,
            text: keyword.text,
            categoryCodes: keyword.codes,
            level: null,
          })),
          levelScoringEnabled: true,
        },
      }),
    );
    await page.route("**/api/jobs/my-levels?**", (route) =>
      route.fulfill({
        json: {
          jobId: "study-demo-backend",
          taxonomyVersion: examples.version,
          source: "LV_STAT",
          levels: keywords
            .filter((keyword) => keyword.score !== null)
            .map((keyword) => ({
              keywordId: keyword.id,
              text: keyword.text,
              categoryCodes: keyword.codes,
              usedCodes: keyword.used,
              score: keyword.score,
              referenceScore: null,
              referenceKind: null,
              evaluationKind: "CONFIRMED",
              evaluatedAt: "2026-11-28T00:05:00.000Z",
            })),
          sources: [
            {
              id: "lv-stat:synthetic-user",
              kind: "GITHUB",
              title: "synthetic-user",
              simulated: false,
            },
          ],
          labels: labelLine.split(" · "),
          identityVerified: false,
          methodVersion: "lv-stat-s2-20261127",
        },
      }),
    );
    await page.goto("/jobs?job=study-demo-backend&demo=low&view=stats");
    const card = page.locator(".saved-level-radar");
    const radar = page.getByTestId("saved-level-radar");
    await expect(radar).toBeVisible();
    await expect(card).toContainText(labelLine);
    await expect(card).not.toContainText("(더미)");
    await expect(
      radar.locator(
        '[data-series="reference"], [data-series-point="reference"]',
      ),
    ).toHaveCount(0);
    await expect(radar).toHaveAttribute(
      "aria-label",
      "프로그래밍·CS 기초: 내 LV 50.0. 백엔드 개발: 내 LV 40.0. 데이터베이스: 내 LV 30.0. 인프라·배포·운영: 내 LV 20.0",
    );
    expect(
      (await radar
        .locator('polygon[data-series="mine"]')
        .getAttribute("points"))!.split(" "),
    ).toHaveLength(4);
  });

  // 아래는 분석한 회원(작업 공간 자료는 없음)의 공고 상세 역량 분석 탭. 점수 행이 없는 공고에서도 '분석 자료 미등록'을
  // 보이지 않아야 한다(분석은 /analysis에서 이미 끝났다).
  const postingStats = "/jobs?job=study-demo-backend&demo=low&view=stats";
  const unregistered = "분석 자료 미등록";
  const emptyRadar = "현재 표시할 카테고리의 평가 결과가 없습니다.";
  const unclassified = "이 공고의 분류된 역량 정보가 아직 없습니다.";
  type Sentence = { id: string; text: string; codes: string[] };
  type Scored = Sentence & { used: string[]; score: number };

  // 공고 문장(keywords, version이 null이면 분류 버전 없는 공고)과 my-levels의 LV_STAT 답(scored 행)을 흉내 낸다.
  async function analyzedMemberOn(
    page: Page,
    sentences: Sentence[],
    scored: Scored[],
    version: string | null = examples.version,
  ) {
    await account(page, true);
    await page.route("**/api/career", (route) =>
      route.fulfill({ json: { workspace: { runs: [], documents: [] } } }),
    );
    await page.route("**/api/growth", (route) =>
      route.fulfill({ json: { growth: { reviews: [], tasks: [] } } }),
    );
    await page.route("**/api/jobs/keywords?**", (route) =>
      route.fulfill({
        json: {
          source: version ? "SAVED_REVIEW" : "UNAVAILABLE",
          ...(version ? { version } : {}),
          keywords: sentences.map((sentence) => ({
            id: sentence.id,
            text: sentence.text,
            categoryCodes: sentence.codes,
            level: null,
          })),
          levelScoringEnabled: false,
        },
      }),
    );
    const calls = { myLevels: 0 };
    await page.route("**/api/jobs/my-levels?**", (route) => {
      calls.myLevels++;
      return route.fulfill({
        json: {
          jobId: "study-demo-backend",
          taxonomyVersion: version,
          source: "LV_STAT",
          levels: scored.map((row) => ({
            keywordId: row.id,
            text: row.text,
            categoryCodes: row.codes,
            usedCodes: row.used,
            score: row.score,
            referenceScore: null,
            referenceKind: null,
            evaluationKind: "CONFIRMED",
            evaluatedAt: "2026-11-28T00:05:00.000Z",
          })),
          sources: [
            {
              id: "lv-stat:synthetic-user",
              kind: "GITHUB",
              title: "synthetic-user",
              simulated: false,
            },
          ],
          labels: labelLine.split(" · "),
          identityVerified: false,
          methodVersion: "lv-stat-s2-20261127",
        },
      });
    });
    return calls;
  }

  test("an analyzed member sees the empty chart with the labels line, not the registration prompt, when only Q, S or H sentences are on the posting", async ({
    page,
  }) => {
    await analyzedMemberOn(
      page,
      [
        { id: "synthetic-q", text: "합성 품질 문장", codes: ["Q"] },
        { id: "synthetic-s", text: "합성 보안 문장", codes: ["S"] },
        { id: "synthetic-h", text: "합성 장비 문장", codes: ["H"] },
      ],
      [],
    );
    await page.goto(postingStats);
    const card = page.locator(".saved-level-radar");
    await expect(card).toContainText(emptyRadar);
    await expect(card).toContainText(labelLine);
    await expect(page.getByText(unregistered)).toHaveCount(0);
    await expect(page.getByText(unclassified)).toHaveCount(0);
  });

  test("an analyzed member on a posting with no classified sentences sees the empty chart, the labels line and the not-yet-classified note", async ({
    page,
  }) => {
    await analyzedMemberOn(page, [], []);
    await page.goto(postingStats);
    const card = page.locator(".saved-level-radar");
    await expect(card).toContainText(emptyRadar);
    await expect(card).toContainText(labelLine);
    await expect(page.getByText(unclassified)).toBeVisible();
    await expect(page.getByText(unregistered)).toHaveCount(0);
  });

  test("on a posting without a classification version, an analysis profile counts as the member's source; a 404 or no profile does not", async ({
    page,
  }) => {
    const calls = await analyzedMemberOn(page, [], [], null);
    let reply: Reply = {
      status: 200,
      json: {
        job: job({ status: "done", stage: "끝" }),
        profile: syntheticProfile("screen-member"),
      },
    };
    let reads = 0;
    await page.route("**/api/lv-stat/analysis", (route) => {
      reads++;
      return route.fulfill(reply);
    });
    await page.goto(postingStats);
    await expect(page.getByText(unclassified)).toBeVisible();
    await expect(page.getByText(unregistered)).toHaveCount(0);
    expect(reads).toBe(1);
    // 스위치가 꺼진 서버(404)나 분석 결과가 없는 회원은 자료가 없다(지금처럼 '미등록').
    for (const next of [
      { status: 404, json: { error: "GitHub 분석을 쓸 수 없어요." } },
      { status: 200, json: { job: null, profile: null } },
    ]) {
      reply = next;
      await page.reload();
      await expect(
        page.getByRole("heading", { name: unregistered, exact: true }),
      ).toBeVisible();
    }
    expect(calls.myLevels).toBe(0);
  });

  test("an analysis that scores only two categories shows the numbers line and the labels line instead of a chart", async ({
    page,
  }) => {
    const sentences = [
      { id: "synthetic-l", text: "합성 문장 하나", codes: ["L"] },
      { id: "synthetic-b", text: "합성 문장 둘", codes: ["B"] },
    ];
    await analyzedMemberOn(page, sentences, [
      { ...sentences[0], used: ["L"], score: 50 },
      { ...sentences[1], used: ["B"], score: 40 },
    ]);
    await page.goto(postingStats);
    const card = page.locator(".saved-level-radar");
    await expect(card).toContainText(
      "프로그래밍·CS 기초 LV 50.0, 백엔드 개발 LV 40.0",
    );
    await expect(card).toContainText(labelLine);
    await expect(card).not.toContainText("(더미)");
    await expect(page.getByTestId("saved-level-radar")).toHaveCount(0);
    await expect(page.getByText(unregistered)).toHaveCount(0);
  });
});
