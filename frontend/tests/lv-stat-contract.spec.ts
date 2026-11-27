import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { registerHooks } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { detectLanguages, scoreKeyword } from "@/lib/lv-stat/score";
import type * as LvStore from "@/lib/server/lv-stat";
import type {
  LvCategory,
  LvCategoryCode,
  LvJob,
  LvProfile,
} from "@/types/lv-stat";

// lib/server 모듈은 `import "server-only"`로 시작한다. Next 서버 빌드는 이것을 빈 모듈로 바꾸는데
// (next/dist/build/create-compiler-aliases.js), 이 시험은 Next 밖(Node)에서 돌아 같은 빈 모듈로 잇는다.
// 정적 import는 이 줄보다 먼저 읽히므로 그런 모듈은 시험 안에서 동적 import로 읽는다.
const serverOnly = registerHooks({
  resolve: (specifier, context, nextResolve) =>
    nextResolve(
      specifier === "server-only"
        ? "next/dist/compiled/server-only/empty"
        : specifier,
      context,
    ),
});
test.afterAll(() => serverOnly.deregister());

type OtherCode = Exclude<LvCategoryCode, "L">;
const names: Record<OtherCode, string> = {
  O: "운영 배포",
  B: "백엔드 개발",
  E: "데이터 엔지니어",
  D: "데이터베이스",
  F: "프론트엔드 앱",
  A: "AI 기술",
};

// 합성 프로필(CONTRACT.md 모양). L은 Java 3.3·Python 2.0이고 가장 높은 언어는 Java다.
// 나머지 카테고리는 준 LV(null이면 판정 불가)이고, 주지 않으면 0.0이다.
function profile(
  lvs: Partial<Record<OtherCode, number | null>> = {},
): LvProfile {
  const box = (code: OtherCode): LvCategory => {
    const lv = lvs[code];
    return { name: names[code], lv: lv === undefined ? 0 : lv, unknown: 0 };
  };
  return {
    schema: "lv-stat-profile/1",
    method: "lv-stat-s2-20261127",
    labels: ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"],
    namespace: "staging",
    subjectId: "synthetic-subject",
    login: "synthetic-user",
    jobId: "00000000-0000-4000-8000-000000000000",
    analyzedAt: "2026-11-28T00:00:00+09:00",
    repos: { found: 1, analyzed: 1, failed: 0, notes: [] },
    categories: {
      L: {
        name: "프로그래밍 활용",
        lv: 3.3,
        unknown: 0,
        languages: { Java: 3.3, Python: 2.0 },
        best: "Java",
      },
      O: box("O"),
      B: box("B"),
      E: box("E"),
      D: box("D"),
      F: box("F"),
      A: box("A"),
    },
  };
}

// L 언어만 바꾼 합성 프로필. lv·best(가장 높은 언어)는 시험에서 손으로 준다.
function withLanguages(
  languages: Record<string, number>,
  lv: number,
  best: string,
): LvProfile {
  const p = profile();
  return {
    ...p,
    categories: {
      ...p.categories,
      L: { ...p.categories.L, lv, languages, best },
    },
  };
}

function scoreOf(p: LvProfile, text: string, categoryCodes: string[]) {
  return scoreKeyword(p, { text, categoryCodes });
}

test.describe("score", () => {
  test("Java but not JavaScript", () => {
    expect(detectLanguages("Java/Spring 경험")).toEqual(["Java"]);
    expect(detectLanguages("JavaScript 경험")).toEqual(["JavaScript"]);
  });

  test("Korean names", () => {
    expect(detectLanguages("자바 또는 파이썬")).toEqual(["Java", "Python"]);
    expect(detectLanguages("자바스크립트")).toEqual(["JavaScript"]);
  });

  test("Go and C are case-sensitive words", () => {
    expect(detectLanguages("Go 언어")).toEqual(["Go"]);
    expect(detectLanguages("go to market")).toEqual([]);
    expect(detectLanguages("C/C++")).toEqual(["C", "C++"]);
    expect(detectLanguages("C#")).toEqual(["C#"]);
  });

  test("JavaScript written with a space is not Java", () => {
    expect(detectLanguages("Java Script 경험")).toEqual(["JavaScript"]);
    expect(detectLanguages("자바 스크립트 경험")).toEqual(["JavaScript"]);
  });

  test("C inside B2C or Objective-C is not C", () => {
    expect(detectLanguages("B2C 서비스 개발")).toEqual([]);
    expect(detectLanguages("Swift, Objective-C 경험")).toEqual([
      "Swift",
      "Objective-C",
    ]);
    expect(detectLanguages("C언어 가능자")).toEqual(["C"]);
  });

  test("SQL is a language, MySQL and NoSQL are not", () => {
    expect(detectLanguages("SQL 활용 능력")).toEqual(["SQL"]);
    expect(detectLanguages("PL/SQL 또는 T-SQL")).toEqual(["SQL"]);
    expect(detectLanguages("MySQL, PostgreSQL, NoSQL, SQLite")).toEqual([]);
  });

  test("R is a word on its own, not in R&D, AR/VR or R-CNN", () => {
    expect(detectLanguages("Python 또는 R 활용")).toEqual(["Python", "R"]);
    expect(detectLanguages("Python/R 분석")).toEqual(["Python", "R"]);
    expect(detectLanguages("R언어 통계 분석")).toEqual(["R"]);
    expect(detectLanguages("R&D 경험, R&R 정의")).toEqual([]);
    expect(detectLanguages("AR/VR 서비스, Faster R-CNN")).toEqual([]);
  });

  test("Shell takes Bash and Korean names, PowerShell is its own", () => {
    const rows: [string, string[]][] = [
      ["Shell, Python 스크립트 작성", ["Python", "Shell"]],
      ["Bash 스크립트", ["Shell"]],
      ["리눅스 쉘 스크립트", ["Shell"]],
      ["유닉스셸 명령", ["Shell"]],
      ["PowerShell 스크립트", ["PowerShell"]],
      ["Power Shell 스크립트", ["PowerShell"]],
      ["파워쉘 스크립트", ["PowerShell"]],
      ["파워 셸 스크립트", ["PowerShell"]],
    ];
    for (const [text, want] of rows)
      expect(detectLanguages(text), text).toEqual(want);
  });

  test("dictionary returns Linguist names", () => {
    const rows: [string, string[]][] = [
      ["JAVA, python 개발", ["Java", "Python"]],
      ["Java8 또는 Python3", ["Java", "Python"]],
      ["코틀린과 타입스크립트", ["Kotlin", "TypeScript"]],
      ["Golang, Rust", ["Go", "Rust"]],
      ["GoLang", ["Go"]],
      ["c++, c#", ["C++", "C#"]],
      [
        "Swift, Dart, Ruby, PHP7, Scala",
        ["Swift", "Dart", "Ruby", "PHP", "Scala"],
      ],
      ["Lua, Groovy, CUDA11", ["Lua", "Groovy", "Cuda"]],
      ["C#, F#", ["C#", "F#"]],
    ];
    for (const [text, want] of rows)
      expect(detectLanguages(text), text).toEqual(want);
  });

  test("multi-category mean", () => {
    expect(
      scoreOf(profile({ B: 3.0, D: 2.0 }), "REST API와 DB 설계", ["B", "D"]),
    ).toEqual({ score: 50, used: ["B", "D"] });
  });

  test("L uses named language", () => {
    expect(scoreOf(profile(), "Python 개발", ["L"])).toEqual({
      score: 40,
      used: ["L"],
    });
    // 섞인 문장에서도 언어 값은 L에만 쓴다: (Python 2.0 + B 3.0) ÷ 2 × 20 = 50
    expect(scoreOf(profile({ B: 3.0 }), "Python 개발", ["L", "B"])).toEqual({
      score: 50,
      used: ["L", "B"],
    });
  });

  test("L takes the highest named language", () => {
    // Kotlin·Scala는 안 써서 0, Python 2.0 → 가장 높은 2.0 × 20 = 40
    expect(scoreOf(profile(), "Kotlin, Python 또는 Scala", ["L"])).toEqual({
      score: 40,
      used: ["L"],
    });
  });

  test("L named but unused language is 0", () => {
    expect(scoreOf(profile(), "Kotlin 개발", ["L"])).toEqual({
      score: 0,
      used: ["L"],
    });
  });

  test("L without language uses best", () => {
    expect(scoreOf(profile(), "자료구조와 알고리즘 이해", ["L"])).toEqual({
      score: 66,
      used: ["L"],
    });
  });

  test("L uses SQL, R and Shell values the worker writes", () => {
    // SQL 0.5 × 20 = 10. SQL을 못 찾으면 언어 없는 문장이 되어 L LV 3.3으로 66이 된다.
    const sql = withLanguages({ Java: 3.3, SQL: 0.5 }, 3.3, "Java");
    expect(scoreOf(sql, "SQL 활용 능력", ["L"])).toEqual({
      score: 10,
      used: ["L"],
    });
    // R 3.5와 Python 1.0 중 높은 3.5 × 20 = 70. R을 못 찾으면 Python만 남아 20이 된다.
    const r = withLanguages({ R: 3.5, Python: 1.0 }, 3.5, "R");
    expect(scoreOf(r, "Python 또는 R 활용", ["L"])).toEqual({
      score: 70,
      used: ["L"],
    });
    // Shell 3.0과 Python 0.5 중 높은 3.0 × 20 = 60. Shell을 못 찾으면 10이 된다.
    const shell = withLanguages({ Shell: 3.0, Python: 0.5 }, 3.0, "Shell");
    expect(scoreOf(shell, "Shell, Python 스크립트 작성", ["L"])).toEqual({
      score: 60,
      used: ["L"],
    });
  });

  test("L finds the person's own languages outside the dictionary", () => {
    const p = withLanguages({ Elixir: 4.0, Python: 1.0 }, 4.0, "Elixir");
    // 사전에 없는 Elixir도 그 사람의 언어라 대소문자 없이 찾는다: 높은 4.0 × 20 = 80.
    // 사전만 보면 Python만 남아 20이 된다.
    expect(scoreOf(p, "Python, elixir 경험", ["L"])).toEqual({
      score: 80,
      used: ["L"],
    });
    // 문장에 적히지 않은 언어는 넣지 않는다: Python 1.0 × 20 = 20
    expect(scoreOf(p, "Python 경험", ["L"])).toEqual({
      score: 20,
      used: ["L"],
    });
    // 이름의 +도 글자 그대로 찾는다: Objective-C++ 4.0 × 20 = 80
    // (사전의 Objective-C도 걸리지만 이 사람은 안 써서 0이다)
    const objcpp = withLanguages(
      { "Objective-C++": 4.0, Python: 1.0 },
      4.0,
      "Objective-C++",
    );
    expect(scoreOf(objcpp, "Objective-C++ 경험", ["L"])).toEqual({
      score: 80,
      used: ["L"],
    });
  });

  test("own-language names match whole words only", () => {
    // Redis의 Red, Clean의 Lean은 언어가 아니다: JavaScript 1.0 × 20 = 20
    const p = withLanguages(
      { Red: 4.0, Lean: 4.0, JavaScript: 1.0 },
      4.0,
      "Red",
    );
    expect(
      scoreOf(p, "Redis 캐시와 Clean Code, JavaScript 개발", ["L"]),
    ).toEqual({ score: 20, used: ["L"] });
  });

  test("short own-language names need clear word edges", () => {
    // 두 글자 이하 이름(D·Io)은 대소문자를 가리고 영문·숫자·_·&·-에 붙은 것을 세지 않는다.
    const p = withLanguages({ D: 4.0, Io: 4.0, Python: 1.0 }, 4.0, "D");
    // R&D의 D와 socket.io의 io는 언어가 아니다: Python 1.0 × 20 = 20
    expect(scoreOf(p, "R&D 부서에서 socket.io와 Python 개발", ["L"])).toEqual({
      score: 20,
      used: ["L"],
    });
    // 따로 적힌 D는 언어다: 높은 4.0 × 20 = 80
    expect(scoreOf(p, "D, Python 개발", ["L"])).toEqual({
      score: 80,
      used: ["L"],
    });
  });

  test("dictionary names keep dictionary rules", () => {
    // Java는 사전 규칙으로만 찾으므로 "Java Script"는 JavaScript(안 써서 0)다.
    // 이름 그대로 다시 찾으면 Java 3.3이 걸려 66이 된다.
    expect(scoreOf(profile(), "Java Script 경험", ["L"])).toEqual({
      score: 0,
      used: ["L"],
    });
  });

  test("Q-only sentence has no score", () => {
    expect(scoreOf(profile(), "단위 테스트 작성", ["Q"])).toEqual({
      score: null,
      used: [],
    });
    expect(
      scoreOf(profile(), "보안 점검과 장비 연동", ["Q", "S", "H"]),
    ).toEqual({ score: null, used: [] });
  });

  test("Q, S, H and aux codes are dropped from the mean", () => {
    expect(
      scoreOf(profile({ B: 3.0 }), "테스트하기 쉬운 API 설계", [
        "Q",
        "B",
        "S",
        "H",
        "T",
        "OTHER",
      ]),
    ).toEqual({ score: 60, used: ["B"] });
  });

  test("null lv category dropped", () => {
    expect(
      scoreOf(profile({ B: 3.0, D: null }), "API와 DB 설계", ["B", "D"]),
    ).toEqual({ score: 60, used: ["B"] });
    expect(scoreOf(profile({ D: null }), "DB 설계", ["D"])).toEqual({
      score: null,
      used: [],
    });
  });

  test("repeated codes count once", () => {
    // B·D 한 번씩: (3.0 + 2.0) ÷ 2 × 20 = 50. B를 두 번 세면 53이 된다.
    expect(
      scoreOf(profile({ B: 3.0, D: 2.0 }), "API와 DB 설계", ["B", "B", "D"]),
    ).toEqual({ score: 50, used: ["B", "D"] });
  });

  test("clamped integer 0..100", () => {
    // (3.0 + 2.0 + 2.0) ÷ 3 × 20 = 46.67 → 47
    expect(
      scoreOf(profile({ B: 3.0, D: 2.0, E: 2.0 }), "데이터 서비스 개발", [
        "B",
        "D",
        "E",
      ]).score,
    ).toBe(47);
    // CONTRACT 범위(0.0~5.0) 밖 값이 와도 0~100 안에 둔다
    expect(scoreOf(profile({ B: 5.6 }), "API 개발", ["B"]).score).toBe(100);
    expect(scoreOf(profile({ B: -0.4 }), "API 개발", ["B"]).score).toBe(0);
  });

  test("exact half rounds up", () => {
    // (0.0 + 0.0 + 0.1 + 4.6) ÷ 4 = 1.175, × 20 = 23.5 → 24.
    // 부동소수로 평균을 내면 23.4999…가 되어 23으로 내려간다.
    expect(
      scoreOf(
        profile({ B: 0, D: 0, E: 0.1, O: 4.6 }),
        "데이터 파이프라인 운영",
        ["B", "D", "E", "O"],
      ).score,
    ).toBe(24);
  });
});

test.describe("store", () => {
  let store: typeof LvStore;
  let dataDir: string;
  let previousDataDir: string | undefined;

  const busy = "이미 분석 중이에요. 끝나면 다시 시도해 주세요.";
  const full = "지금 분석 요청이 많아요. 잠시 뒤 다시 시도해 주세요.";
  const uuidV4 =
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const lvDir = () => path.join(dataDir, "lv-stat");
  const jobsDir = () => path.join(lvDir(), "jobs");
  const profilesDir = () => path.join(lvDir(), "profiles");

  test.beforeAll(async () => {
    store = await import("@/lib/server/lv-stat");
  });

  test.beforeEach(async () => {
    previousDataDir = process.env.CAREER_DATA_DIR;
    dataDir = await mkdtemp(path.join(tmpdir(), "lv-stat-store-"));
    process.env.CAREER_DATA_DIR = dataDir;
  });

  test.afterEach(async () => {
    if (previousDataDir === undefined) delete process.env.CAREER_DATA_DIR;
    else process.env.CAREER_DATA_DIR = previousDataDir;
    await rm(dataDir, { recursive: true, force: true });
  });

  // CONTRACT의 profileKey를 시험에서 따로 계산한다: sha256(namespace + ":" + subjectId)의 앞 32자.
  const contractKey = (namespace: string, subjectId: string) =>
    createHash("sha256")
      .update(`${namespace}:${subjectId}`)
      .digest("hex")
      .slice(0, 32);
  const profileFile = (namespace: string, subjectId: string) =>
    path.join(profilesDir(), `${contractKey(namespace, subjectId)}.json`);

  function jobRequest(subjectId: string, namespace = "staging") {
    return {
      namespace,
      subjectId,
      login: "synthetic-user",
      input: "https://github.com/synthetic-user",
    };
  }

  // 웹이 만든 요청 파일(CONTRACT 처음 모양). 작업자가 더하는 칸은 fields로 준다.
  function jobFile(id: string, fields: Record<string, unknown> = {}) {
    return {
      id,
      ...jobRequest("subject-a"),
      status: "queued",
      createdAt: "2026-11-28T00:00:00.000Z",
      ...fields,
    };
  }

  async function writeJson(file: string, value: unknown) {
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, JSON.stringify(value));
  }

  // 작업자처럼 요청 파일에 칸을 더해 바꾼다(같은 폴더 임시 파일 + rename).
  async function workerUpdate(id: string, fields: Partial<LvJob>) {
    const file = path.join(jobsDir(), `${id}.json`);
    const job = JSON.parse(await readFile(file, "utf8"));
    await writeFile(`${file}.tmp`, JSON.stringify({ ...job, ...fields }));
    await rename(`${file}.tmp`, file);
  }

  function rejections(results: PromiseSettledResult<unknown>[]) {
    return results.flatMap((result) =>
      result.status === "rejected" ? [result.reason] : [],
    );
  }

  // 작업자가 쓰는 결과 모양(calc.py): B 칸에는 note가 더 있다.
  function storedProfile(subjectId: string) {
    const p = profile({ B: 2.0, D: null });
    return {
      ...p,
      subjectId,
      categories: {
        ...p.categories,
        B: { ...p.categories.B, note: "백엔드 게이트 통과 레포 1개" },
      },
    };
  }

  // value를 깊이 복사해 점으로 이은 칸 하나를 바꾼다(field가 undefined면 그 칸을 지운다).
  function withField(value: unknown, dotted: string, field: unknown) {
    const copy = structuredClone(value) as Record<string, unknown>;
    const keys = dotted.split(".");
    let node = copy;
    for (const key of keys.slice(0, -1))
      node = node[key] as Record<string, unknown>;
    const last = keys[keys.length - 1];
    if (field === undefined) delete node[last];
    else node[last] = field;
    return copy;
  }

  test("lvDataDir follows CAREER_DATA_DIR", () => {
    // store.ts의 db()와 같은 기준이고, 부를 때마다 환경 변수를 읽는다.
    expect(store.lvDataDir()).toBe(path.join(dataDir, "lv-stat"));
    process.env.CAREER_DATA_DIR = path.join(dataDir, "other");
    expect(store.lvDataDir()).toBe(path.join(dataDir, "other", "lv-stat"));
    process.env.CAREER_DATA_DIR = "";
    expect(store.lvDataDir()).toBe(
      path.join(process.cwd(), ".career-data", "lv-stat"),
    );
  });

  test("profileKey matches sha256 prefix", () => {
    // Python 작업자와 같은 값: hashlib.sha256("staging:abc".encode()).hexdigest()[:32]
    expect(store.profileKey("staging", "abc")).toBe(
      "96fa33204c6efc31b9fc11b945580806",
    );
  });

  test("parseGithubLogin accepts account and repo URLs", () => {
    const rows: [string, string][] = [
      ["https://github.com/synthetic-user", "synthetic-user"],
      ["https://github.com/synthetic-user/", "synthetic-user"],
      ["https://www.github.com/synthetic-user", "synthetic-user"],
      ["https://GitHub.com/Synthetic-User", "Synthetic-User"],
      ["https://github.com/synthetic-user/sample-repo", "synthetic-user"],
      ["https://github.com/synthetic-user/sample-repo/", "synthetic-user"],
      ["https://github.com/synthetic-user/sample.repo_2.git", "synthetic-user"],
      ["https://github.com/synthetic-user/sample-repo.git/", "synthetic-user"],
      ["https://github.com/a1-b2-c3", "a1-b2-c3"],
      [`https://github.com/${"a".repeat(39)}`, "a".repeat(39)],
      [
        `https://github.com/synthetic-user/${"r".repeat(100)}`,
        "synthetic-user",
      ],
    ];
    for (const [input, login] of rows)
      expect(store.parseGithubLogin(input), input).toBe(login);
  });

  test("rejects other hosts, credentials, ports, queries, bad logins", () => {
    const rows = [
      // https만
      "http://github.com/synthetic-user",
      "github.com/synthetic-user",
      "//github.com/synthetic-user",
      // 다른 호스트
      "https://gitlab.com/synthetic-user",
      "https://gist.github.com/synthetic-user",
      "https://api.github.com/users/synthetic-user",
      "https://github.com.example.com/synthetic-user",
      "https://examplegithub.com/synthetic-user",
      // 사용자·암호(빈 것도)
      "https://synthetic:x@github.com/synthetic-user",
      "https://synthetic@github.com/synthetic-user",
      "https://@github.com/synthetic-user",
      // 포트(기본 포트 443도)
      "https://github.com:443/synthetic-user",
      "https://github.com:8443/synthetic-user",
      // 쿼리·조각(빈 것도)
      "https://github.com/synthetic-user?tab=repositories",
      "https://github.com/synthetic-user?",
      "https://github.com/synthetic-user/sample-repo?ref=main",
      "https://github.com/synthetic-user#readme",
      "https://github.com/synthetic-user/sample-repo#",
      // 경로가 /<아이디> 또는 /<아이디>/<레포>가 아님
      "https://github.com",
      "https://github.com/",
      "https://github.com//synthetic-user",
      "https://github.com/synthetic-user//",
      "https://github.com/synthetic-user/sample-repo/tree/main",
      // 레포 이름 규칙(GitHub: 100자 이하)
      `https://github.com/synthetic-user/${"r".repeat(101)}`,
      // 아이디 규칙(작업자와 같음)
      "https://github.com/-synthetic",
      "https://github.com/synthetic-",
      "https://github.com/synthetic--user",
      "https://github.com/synthetic_user",
      "https://github.com/synthetic.user",
      "https://github.com/%73ynthetic",
      `https://github.com/${"a".repeat(40)}`,
      // 저장하는 input이 검사한 주소 그대로이게 공백·줄바꿈도 받지 않는다(URL 파서는 지운다).
      " https://github.com/synthetic-user",
      "https://github.com/synthetic-user\n",
      "https://github.com/synthetic\n-user",
      "",
    ];
    for (const input of rows)
      expect(store.parseGithubLogin(input), JSON.stringify(input)).toBeNull();
  });

  test("createJob writes queued job", async () => {
    const before = Date.now();
    const job = await store.createJob({
      namespace: "staging",
      subjectId: "subject-a",
      login: "synthetic-user",
      input: "https://github.com/synthetic-user/sample-repo",
    });
    expect(job).toEqual({
      id: expect.stringMatching(uuidV4),
      namespace: "staging",
      subjectId: "subject-a",
      login: "synthetic-user",
      input: "https://github.com/synthetic-user/sample-repo",
      status: "queued",
      createdAt: expect.any(String),
    });
    // createdAt은 지금 시각의 ISO 8601(UTC)이다.
    expect(new Date(job.createdAt).toISOString()).toBe(job.createdAt);
    expect(Date.parse(job.createdAt)).toBeGreaterThanOrEqual(before);
    expect(Date.parse(job.createdAt)).toBeLessThanOrEqual(Date.now());
    // jobs/<id>.json에 CONTRACT의 처음 모양 그대로 쓴다. 폴더 0700, 파일 0600.
    const file = path.join(jobsDir(), `${job.id}.json`);
    expect(JSON.parse(await readFile(file, "utf8"))).toEqual(job);
    expect((await stat(lvDir())).mode & 0o777).toBe(0o700);
    expect((await stat(jobsDir())).mode & 0o777).toBe(0o700);
    expect((await stat(file)).mode & 0o777).toBe(0o600);
  });

  test("rejects second active job", async () => {
    const first = await store.createJob(jobRequest("subject-a"));
    const second = store.createJob(jobRequest("subject-a"));
    await expect(second).rejects.toBeInstanceOf(store.LvStatError);
    await expect(second).rejects.toMatchObject({ message: busy, status: 409 });
    // 작업자가 집어 running이 되어도 진행 중이다.
    await workerUpdate(first.id, {
      status: "running",
      stage: "레포 받기",
      startedAt: new Date().toISOString(),
    });
    await expect(
      store.createJob(jobRequest("subject-a")),
    ).rejects.toMatchObject({ message: busy, status: 409 });
    // 다른 사람(다른 subject, 다른 namespace의 같은 subject)은 막지 않는다.
    await expect(
      store.createJob(jobRequest("subject-b")),
    ).resolves.toMatchObject({ subjectId: "subject-b", status: "queued" });
    await expect(
      store.createJob(jobRequest("subject-a", "other-namespace")),
    ).resolves.toMatchObject({
      namespace: "other-namespace",
      subjectId: "subject-a",
      status: "queued",
    });
    expect(await readdir(jobsDir())).toHaveLength(3);
  });

  test("parallel requests for one person make one job", async () => {
    // 같은 사람 확인과 파일 쓰기 사이에 다른 요청이 끼면 둘 다 들어간다.
    const results = await Promise.allSettled(
      [1, 2, 3].map(() => store.createJob(jobRequest("subject-a"))),
    );
    const rejected = rejections(results);
    expect(rejected).toHaveLength(2);
    for (const reason of rejected)
      expect(reason).toMatchObject({ message: busy, status: 409 });
    expect(await readdir(jobsDir())).toHaveLength(1);
  });

  test("allows new job after failure", async () => {
    const first = await store.createJob(jobRequest("subject-a"));
    // 작업자가 집었다가, 다시 시작되며 진행 중이던 요청을 실패로 닫는다(작업자 recover).
    await workerUpdate(first.id, {
      status: "running",
      stage: "색인",
      startedAt: new Date().toISOString(),
    });
    await workerUpdate(first.id, {
      status: "failed",
      stage: "실패",
      error: "작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.",
      finishedAt: new Date().toISOString(),
    });
    // 두 요청의 createdAt이 같은 밀리초가 되지 않게 조금 기다린다.
    await new Promise((resolve) => setTimeout(resolve, 5));
    const second = await store.createJob(jobRequest("subject-a"));
    expect(second.id).not.toBe(first.id);
    expect(await store.latestJob("staging", "subject-a")).toEqual(second);
    // 끝난(done) 요청도 막지 않는다.
    await workerUpdate(second.id, {
      status: "done",
      stage: "끝",
      finishedAt: new Date().toISOString(),
    });
    await expect(
      store.createJob(jobRequest("subject-a")),
    ).resolves.toMatchObject({ subjectId: "subject-a", status: "queued" });
  });

  test("global queue cap 20", async () => {
    // 「Claude 임시값」 전체 대기 20건. 19건이 대기 중이면 한 자리가 남는다.
    const queued: LvJob[] = [];
    for (let i = 0; i < 19; i++)
      queued.push(await store.createJob(jobRequest(`subject-${i}`)));
    // 남은 한 자리를 세 사람이 함께 요청하면 한 사람만 들어간다.
    const results = await Promise.allSettled(
      ["x", "y", "z"].map((s) => store.createJob(jobRequest(`subject-${s}`))),
    );
    const rejected = rejections(results);
    expect(rejected).toHaveLength(2);
    for (const reason of rejected) {
      expect(reason).toBeInstanceOf(store.LvStatError);
      expect(reason).toMatchObject({ message: full, status: 503 });
    }
    // 대기(queued)만 센다: 작업자가 하나를 집고(running) 하나가 실패로 끝나면 두 자리가 빈다.
    await workerUpdate(queued[0].id, { status: "running" });
    await workerUpdate(queued[1].id, { status: "failed" });
    for (const subject of ["subject-late-1", "subject-late-2"])
      await expect(store.createJob(jobRequest(subject))).resolves.toMatchObject(
        { subjectId: subject, status: "queued" },
      );
    await expect(
      store.createJob(jobRequest("subject-late-3")),
    ).rejects.toMatchObject({ message: full, status: 503 });
  });

  test("latestJob is per subject", async () => {
    expect(await store.latestJob("staging", "subject-a")).toBeNull();
    // 파일 이름 순서와 createdAt 순서를 다르게 둔다.
    const files = [
      jobFile("11111111-1111-4111-8111-111111111111", {
        status: "failed",
        createdAt: "2026-11-28T02:00:00.000Z",
      }),
      jobFile("22222222-2222-4222-8222-222222222222", {
        status: "done",
        createdAt: "2026-11-28T03:00:00.000Z",
        stage: "끝",
        progress: { done: 3, total: 3 },
        startedAt: "2026-11-28T03:00:01.000Z",
        finishedAt: "2026-11-28T03:05:00.000Z",
        profileKey: contractKey("staging", "subject-a"),
      }),
      jobFile("33333333-3333-4333-8333-333333333333", {
        status: "failed",
        createdAt: "2026-11-28T01:00:00.000Z",
      }),
      jobFile("44444444-4444-4444-8444-444444444444", {
        subjectId: "subject-b",
        createdAt: "2026-11-28T04:00:00.000Z",
        stage: "대기",
        progress: null,
      }),
      jobFile("55555555-5555-4555-8555-555555555555", {
        namespace: "other-namespace",
        createdAt: "2026-11-28T05:00:00.000Z",
      }),
    ];
    for (const file of files)
      await writeJson(path.join(jobsDir(), `${file.id}.json`), file);
    expect(await store.latestJob("staging", "subject-a")).toEqual(files[1]);
    expect(await store.latestJob("staging", "subject-b")).toEqual(files[3]);
    expect(await store.latestJob("other-namespace", "subject-a")).toEqual(
      files[4],
    );
    expect(await store.latestJob("staging", "subject-c")).toBeNull();
  });

  test("latestJob keeps only contract fields", async () => {
    const id = "66666666-6666-4666-8666-666666666666";
    const file = path.join(jobsDir(), `${id}.json`);
    const done = jobFile(id, {
      status: "done",
      stage: "끝",
      progress: { done: 2, total: 2 },
      startedAt: "2026-11-28T00:00:01.000Z",
      finishedAt: "2026-11-28T00:09:00.000Z",
      profileKey: contractKey("staging", "subject-a"),
    });
    // 성공 때 error: null이나 CONTRACT에 없는 칸이 와도 CONTRACT 칸만 돌려준다(화면으로 가는 값).
    await writeJson(file, {
      ...done,
      error: null,
      workDir: "/srv/synthetic/work",
    });
    expect(await store.latestJob("staging", "subject-a")).toEqual(done);
    // 작업자 칸의 모양이 틀리면 그 칸만 버린다. 요청은 그대로 진행 중으로 세어 다음 요청을 막는다.
    const running = jobFile(id, { status: "running" });
    await writeJson(file, {
      ...running,
      stage: "없는 단계",
      progress: { done: "1", total: 3 },
      startedAt: 7,
      error: ["x"],
    });
    expect(await store.latestJob("staging", "subject-a")).toEqual(running);
    await expect(
      store.createJob(jobRequest("subject-a")),
    ).rejects.toMatchObject({ message: busy, status: 409 });
  });

  test("latestJob skips jobs with broken web fields", async () => {
    const good = jobFile("99999999-9999-4999-8999-999999999999", {
      status: "failed",
    });
    await writeJson(path.join(jobsDir(), `${good.id}.json`), good);
    // 웹이 쓰는 칸이 틀린 요청 파일은 없는 것으로 본다. 모두 같은 사람의 더 늦은 대기 요청이라,
    // 읽히면 latestJob이 바뀌거나 다음 요청이 막힌다.
    const broken: [string, unknown][] = [
      ["login", undefined],
      ["input", null],
      ["status", "paused"],
      ["createdAt", "어제"],
      ["createdAt", undefined],
    ];
    for (const [index, [field, value]] of broken.entries()) {
      const id = `aaaaaaa${index}-aaaa-4aaa-8aaa-aaaaaaaaaaaa`;
      await writeJson(
        path.join(jobsDir(), `${id}.json`),
        withField(
          jobFile(id, { createdAt: "2099-01-01T00:00:00.000Z" }),
          field,
          value,
        ),
      );
    }
    expect(await store.latestJob("staging", "subject-a")).toEqual(good);
    await expect(
      store.createJob(jobRequest("subject-a")),
    ).resolves.toMatchObject({ subjectId: "subject-a", status: "queued" });
  });

  test("readProfile ignores other subjects and bad schema", async () => {
    const mine = storedProfile("subject-a");
    await writeJson(profileFile("staging", "subject-a"), mine);
    expect(await store.readProfile("staging", "subject-a")).toEqual(mine);
    // 다른 사람·다른 namespace의 결과는 없다.
    expect(await store.readProfile("staging", "subject-b")).toBeNull();
    expect(await store.readProfile("other-namespace", "subject-a")).toBeNull();
    // 그 사람 자리의 파일이어도 안의 사람(namespace+subjectId)이 다르면 그 사람 결과가 아니다.
    await writeJson(profileFile("staging", "subject-b"), mine);
    expect(await store.readProfile("staging", "subject-b")).toBeNull();
    await writeJson(profileFile("other-namespace", "subject-a"), mine);
    expect(await store.readProfile("other-namespace", "subject-a")).toBeNull();
    // schema가 lv-stat-profile/1이 아니면 null
    for (const schema of ["lv-stat-profile/2", undefined]) {
      await writeJson(
        profileFile("staging", "subject-a"),
        withField(mine, "schema", schema),
      );
      expect(
        await store.readProfile("staging", "subject-a"),
        schema,
      ).toBeNull();
    }
    // 깨진 파일(반쯤 쓴 JSON·빈 파일·객체가 아닌 JSON)은 null
    for (const text of [
      '{"schema": "lv-stat-profile/1", "categories": {',
      "",
      "null",
      "[]",
      '"lv-stat-profile/1"',
    ]) {
      await writeFile(profileFile("staging", "subject-a"), text);
      expect(await store.readProfile("staging", "subject-a"), text).toBeNull();
    }
  });

  test("readProfile rejects shapes scoreKeyword cannot read", async () => {
    // Task 7 scoreKeyword는 7칸(L O B E D F A)과 L.languages(이름 → 수), 0~5 또는 null인 lv를 믿고 읽는다.
    // 화면은 이름·lv·unknown(모름 n개)·labels를, my-levels는 login·method·analyzedAt을 읽는다.
    const broken: [string, unknown][] = [
      ["categories", []],
      ["categories.A", undefined],
      ["categories.E", null],
      ["categories.D.lv", undefined],
      ["categories.F.lv", "2.0"],
      ["categories.B.lv", 5.1],
      ["categories.O.lv", -0.1],
      ["categories.O.unknown", -1],
      ["categories.O.unknown", 0.5],
      ["categories.B.name", 2],
      ["categories.L.languages", undefined],
      ["categories.L.languages", ["Java"]],
      ["categories.L.languages.Java", "3.3"],
      ["categories.L.languages.Java", 6],
      ["categories.L.best", 3],
      ["labels", "2단계 규칙"],
      ["labels", [1]],
      ["method", undefined],
      ["login", null],
      ["jobId", 7],
      ["analyzedAt", "어제"],
      ["repos", undefined],
      ["repos.found", "1"],
      ["repos.analyzed", undefined],
      ["repos.failed", -1],
      ["repos.notes", undefined],
    ];
    for (const [field, value] of broken) {
      await writeJson(
        profileFile("staging", "subject-a"),
        withField(storedProfile("subject-a"), field, value),
      );
      expect(
        await store.readProfile("staging", "subject-a"),
        `${field} = ${JSON.stringify(value)}`,
      ).toBeNull();
    }
    // 판정 불가(lv null)와 언어가 하나도 없는 L은 읽는다.
    let empty = withField(storedProfile("subject-a"), "categories.L.lv", null);
    empty = withField(empty, "categories.L.languages", {});
    empty = withField(empty, "categories.L.best", null);
    await writeJson(profileFile("staging", "subject-a"), empty);
    expect(await store.readProfile("staging", "subject-a")).toEqual(empty);
  });

  test("profile path ignores client input", async () => {
    // subject를 경로에 그대로 이으면 읽히는 미끼: profiles/../decoy.json
    const subjectId = "../decoy";
    const decoy = storedProfile(subjectId);
    await writeJson(path.join(lvDir(), "decoy.json"), decoy);
    expect(await store.readProfile("staging", subjectId)).toBeNull();
    // 결과 파일 이름은 서버가 만든 profileKey뿐이다.
    await writeJson(profileFile("staging", subjectId), decoy);
    expect(await store.readProfile("staging", subjectId)).toEqual(decoy);
  });

  test("job id must be uuid", async () => {
    // 사용자가 넣은 주소는 파일 이름에 쓰지 않는다. 이름은 서버가 만든 uuid v4이고 임시 파일은 남지 않는다.
    const job = await store.createJob({
      ...jobRequest("subject-a"),
      input: "https://github.com/synthetic-user/../../profiles/decoy",
    });
    expect(job.id).toMatch(uuidV4);
    expect(await readdir(lvDir())).toEqual(["jobs"]);
    expect(await readdir(jobsDir())).toEqual([`${job.id}.json`]);
    await workerUpdate(job.id, { status: "failed", stage: "실패" });
    // 이름이 uuid v4 .json이 아니거나 안의 id가 이름과 다른 요청 파일은 읽지 않는다(작업자 list_jobs와 같음).
    // 모두 같은 사람의 더 늦은 대기 요청이라, 읽히면 latestJob이 바뀌고 다음 요청이 막힌다.
    const other = "77777777-7777-4777-8777-777777777777";
    // 대문자 uuid는 다른 이름과 대소문자만 다르면 macOS(대소문자 무시 파일 시스템)에서 겹쳐서 따로 둔다.
    const upper = "ABCDEF01-2345-4678-9ABC-DEF012345678";
    const strays: [name: string, id: string][] = [
      ["active.json", "active"],
      [`${other}.json.tmp`, other],
      [`.${other}.tmp`, other],
      [`${upper}.json`, upper],
      [
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8.json",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      ],
      [`${other}.json`, "88888888-8888-4888-8888-888888888888"],
    ];
    for (const [name, id] of strays)
      await writeJson(
        path.join(jobsDir(), name),
        jobFile(id, { createdAt: "2099-01-01T00:00:00.000Z" }),
      );
    expect(await store.latestJob("staging", "subject-a")).toMatchObject({
      id: job.id,
      status: "failed",
    });
    await expect(
      store.createJob(jobRequest("subject-a")),
    ).resolves.toMatchObject({ subjectId: "subject-a", status: "queued" });
  });
});
