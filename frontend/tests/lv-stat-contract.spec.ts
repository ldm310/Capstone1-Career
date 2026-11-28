import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { registerHooks } from "node:module";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import type * as KeywordsRoute from "@/app/api/jobs/keywords/route";
import type * as MyLevelsRoute from "@/app/api/jobs/my-levels/route";
import type * as AnalysisRoute from "@/app/api/lv-stat/analysis/route";
import { detectLanguages, scoreKeyword } from "@/lib/lv-stat/score";
import type * as DemoAccount from "@/lib/server/demo-account";
import type * as JobKeywords from "@/lib/server/job-keywords";
import type * as LvStore from "@/lib/server/lv-stat";
import type * as ProfileLevels from "@/lib/server/profile-levels";
import type * as Store from "@/lib/server/store";
import examples from "@/mock/reviewed-keyword-examples.json";
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

// CONTRACT의 profileKey를 시험에서 따로 계산한다: sha256(namespace + ":" + subjectId)의 앞 32자.
const contractKey = (namespace: string, subjectId: string) =>
  createHash("sha256")
    .update(`${namespace}:${subjectId}`)
    .digest("hex")
    .slice(0, 32);

// 아무도 듣지 않는 로컬 포트(연결 거부)
async function closedPort() {
  const probe = createServer();
  await new Promise<void>((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const { port } = probe.address() as AddressInfo;
  await new Promise<void>((resolve) => probe.close(() => resolve()));
  return `http://127.0.0.1:${port}`;
}

// 서버 기록(console.error)을 모은다. 실패 경로 시험의 출력이 깨끗하고, 기록에 남는 것을 시험할 수 있다.
function captureErrors() {
  const original = console.error;
  const calls: unknown[][] = [];
  console.error = (...args: unknown[]) => {
    calls.push(args);
  };
  return {
    calls,
    restore: () => {
      console.error = original;
    },
  };
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
    const startedAt = new Date().toISOString();
    await workerUpdate(first.id, {
      status: "running",
      stage: "색인",
      startedAt,
    });
    const error = "작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.";
    const finishedAt = new Date().toISOString();
    await workerUpdate(first.id, {
      status: "failed",
      stage: "실패",
      error,
      finishedAt,
    });
    // 화면은 실패 이유(error)를 그대로 보인다(Review Focus 3). latestJob이 작업자가 더한 칸을 함께 준다.
    expect(await store.latestJob("staging", "subject-a")).toEqual({
      ...first,
      status: "failed",
      stage: "실패",
      startedAt,
      finishedAt,
      error,
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

test.describe("job keywords", () => {
  let jobKeywords: typeof JobKeywords.jobKeywords;
  let GET: typeof KeywordsRoute.GET;
  let server: Server;
  let backend: string;
  let previousUrl: string | undefined;
  let requests: string[] = [];
  let errors: ReturnType<typeof captureErrors>;

  const failure = {
    status: 502,
    body: { error: "공고의 저장된 키워드 분류를 불러오지 못했어요." },
  };
  const unavailable = {
    status: 200,
    body: { source: "UNAVAILABLE", keywords: [], levelScoringEnabled: false },
  };

  // Spring /api/postings/{id}/skill-categories 모양(SkillCategoryService.PostingCategories). 문장은 합성이다.
  const item = (
    itemId: number,
    sourceCategory: string,
    status: string,
    categoryCodes: string[],
    flags: { excludedFromCounts?: boolean; needsReview?: boolean } = {},
  ) => ({
    itemId,
    sourceCategory,
    text: `합성 요건 ${itemId}`,
    assignment: {
      status,
      categoryCodes,
      excludedFromCounts: flags.excludedFromCounts ?? false,
      needsReview: flags.needsReview ?? false,
      relatedGroups: [],
    },
  });
  const saved = {
    postingId: 9001,
    version: "synthetic-v1",
    analysisStatus: "ANALYZED",
    recruitUnits: [
      {
        unitId: 1,
        name: "합성 단위 1",
        items: [
          item(1, "필수", "CLASSIFIED", ["B", "D"]),
          // 한 가지만 어긋나도 빠진다: 카운트 제외, 검토 대기, 아는 코드 없음, 분류 안 됨
          item(2, "필수", "CLASSIFIED", ["B"], { excludedFromCounts: true }),
          item(3, "우대", "CLASSIFIED", ["B"], { needsReview: true }),
          item(4, "우대", "CLASSIFIED", ["X", "OTHER"]),
          item(5, "우대", "UNCLASSIFIED", ["B"]),
          // 모르는 코드만 지운다. Q는 카테고리 10개에 있어 남는다.
          item(6, "우대", "CLASSIFIED", ["T", "Q", "OTHER"]),
        ],
      },
      {
        unitId: 2,
        name: "합성 단위 2",
        items: [item(7, "필수", "CLASSIFIED", ["L"])],
      },
    ],
  };
  // 경로 → [상태, 본문]. 없는 경로는 404, hang은 답하지 않는다.
  const answers: Record<string, [number, string]> = {
    "/api/postings/9001/skill-categories": [200, JSON.stringify(saved)],
    "/api/postings/9002/skill-categories": [
      200,
      JSON.stringify({ ...saved, recruitUnits: [] }),
    ],
    "/api/postings/9003/skill-categories": [200, "not json"],
    "/api/postings/9004/skill-categories": [
      200,
      JSON.stringify({ ...saved, recruitUnits: null }),
    ],
    // 본문 모양이 맞아도 2xx가 아니면 실패다.
    "/api/postings/9005/skill-categories": [500, JSON.stringify(saved)],
    // 끝에 쉼표가 남은 JSON. 해석 오류의 글(SyntaxError message)에 이 문장 일부가 들어간다.
    "/api/postings/9007/skill-categories": [
      200,
      '{"version":"synthetic-v1","recruitUnits":[{"items":[{"text":"합성 요건 99"},]}]}',
    ],
  };
  const hang = "/api/postings/9006/skill-categories";

  test.beforeAll(async () => {
    server = createServer((request, response) => {
      requests.push(request.url!);
      if (request.url === hang) return;
      const [status, body] = answers[request.url!] ?? [404, "{}"];
      response
        .writeHead(status, { "Content-Type": "application/json" })
        .end(body);
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    backend = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    ({ jobKeywords } = await import("@/lib/server/job-keywords"));
    ({ GET } = await import("@/app/api/jobs/keywords/route"));
  });

  test.afterAll(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  test.beforeEach(() => {
    previousUrl = process.env.BACKEND_URL;
    process.env.BACKEND_URL = backend;
    requests = [];
    errors = captureErrors();
  });

  test.afterEach(() => {
    errors.restore();
    if (previousUrl === undefined) delete process.env.BACKEND_URL;
    else process.env.BACKEND_URL = previousUrl;
  });

  test("be:9001 returns classified keywords only", async () => {
    expect(await jobKeywords("be:9001")).toEqual({
      status: 200,
      body: {
        source: "SAVED_REVIEW",
        version: "synthetic-v1",
        keywords: [
          {
            id: "1",
            text: "합성 요건 1",
            requirementType: "필수",
            categoryCodes: ["B", "D"],
            level: null,
          },
          {
            id: "6",
            text: "합성 요건 6",
            requirementType: "우대",
            categoryCodes: ["Q"],
            level: null,
          },
          {
            id: "7",
            text: "합성 요건 7",
            requirementType: "필수",
            categoryCodes: ["L"],
            level: null,
          },
        ],
        levelScoringEnabled: false,
      },
    });
    expect(requests).toEqual(["/api/postings/9001/skill-categories"]);
    // 분류된 문장이 없는 공고는 오류가 아니라 빈 목록이다.
    expect(await jobKeywords("be:9002")).toEqual({
      status: 200,
      body: {
        source: "SAVED_REVIEW",
        version: "synthetic-v1",
        keywords: [],
        levelScoringEnabled: false,
      },
    });
  });

  test("backend down → 502", async () => {
    // 500 응답, 아무도 듣지 않는 포트, 답하지 않는 백엔드(5초 뒤 끊는다)
    expect(await jobKeywords("be:9005")).toEqual(failure);
    process.env.BACKEND_URL = await closedPort();
    expect(await jobKeywords("be:9001")).toEqual(failure);
    process.env.BACKEND_URL = backend;
    expect(await jobKeywords("be:9006")).toEqual(failure);
  });

  test("unreadable backend answer → 502", async () => {
    // 없는 공고(404), JSON이 아닌 본문, recruitUnits가 null
    for (const id of ["be:9999", "be:9003", "be:9004"])
      expect(await jobKeywords(id), id).toEqual(failure);
  });

  test("failures are logged without backend address, body or posting text", async () => {
    // 실패(502)가 아니면 기록하지 않는다: 분류된 공고, 빈 공고, 예시 공고, 다른 id, 잘못된 id, 연결 설정 없음
    for (const id of [
      "be:9001",
      "be:9002",
      "dummy:backend-platform",
      "kr:1",
      "",
    ])
      await jobKeywords(id);
    delete process.env.BACKEND_URL;
    await jobKeywords("be:9001");
    expect(errors.calls).toEqual([]);

    // [BACKEND_URL, 공고 번호, 기록의 error]. 2xx가 아닌 답은 그 상태를 남긴다. fetch·JSON 해석이 던진 오류는
    // 이름만 남긴다: 그 글에는 백엔드 주소(주소 해석·자격 증명 오류)나 응답 본문 일부(JSON 해석 오류)가 들어간다.
    const down = await closedPort();
    const withSecret = backend.replace("http://", "http://lv-user:lv-secret@");
    const rows: [string, string, unknown][] = [
      [backend, "9005", expect.stringMatching(/\b500\b/)],
      [backend, "9999", expect.stringMatching(/\b404\b/)],
      [backend, "9003", "SyntaxError"],
      [backend, "9007", "SyntaxError"],
      [backend, "9004", "TypeError"],
      [down, "9001", "TypeError"],
      [withSecret, "9001", "TypeError"],
      ["not a url", "9001", "TypeError"],
    ];
    for (const [url, posting] of rows) {
      process.env.BACKEND_URL = url;
      expect(await jobKeywords(`be:${posting}`), posting).toEqual(failure);
    }
    expect(errors.calls).toEqual(
      rows.map(([, posting, error]) => [
        "Job keyword lookup failed",
        { postingId: posting, error },
      ]),
    );
    const logged = JSON.stringify(errors.calls);
    for (const leak of [
      new URL(backend).host,
      new URL(down).host,
      "lv-secret",
      "not a url",
      "not json",
      "요건",
    ])
      expect(logged, leak).not.toContain(leak);
  });

  test("no BACKEND_URL → 503", async () => {
    delete process.env.BACKEND_URL;
    expect(await jobKeywords("be:9001")).toEqual({
      status: 503,
      body: { error: "키워드 분류 서버가 연결되지 않았어요." },
    });
    // 예시 공고와 백엔드 공고가 아닌 id는 BACKEND_URL을 보기 전에 답한다.
    expect(await jobKeywords("study-demo-backend")).toMatchObject({
      status: 200,
      body: { source: "EXAMPLE" },
    });
    expect(await jobKeywords("kr:1")).toEqual(unavailable);
  });

  test("bad id → 400", async () => {
    const bad = { status: 400, body: { error: "공고를 확인해 주세요." } };
    // 빈 id와 200자를 넘는 id. 백엔드 공고 모양이어도 백엔드에 묻지 않는다.
    for (const id of ["", "x".repeat(201), `be:${"1".repeat(198)}`])
      expect(await jobKeywords(id), id).toEqual(bad);
    expect(requests).toEqual([]);
    // 200자까지는 id로 받는다.
    expect(await jobKeywords("x".repeat(200))).toEqual(unavailable);
  });

  test("example jobs return the saved examples", async () => {
    // 더미 공고와 화면 시험 공고는 저장된 분류 예시를 그대로 준다(LV 없음).
    for (const id of ["dummy:backend-platform", "study-demo-backend"])
      expect(await jobKeywords(id), id).toEqual({
        status: 200,
        body: {
          source: "EXAMPLE",
          version: examples.version,
          keywords: examples.examples,
          levelScoringEnabled: false,
        },
      });
    expect(requests).toEqual([]);
  });

  test("other ids are unavailable", async () => {
    for (const id of ["kr:1", "be:0", "be:01", "be:1.5", "BE:1", "be:1 "])
      expect(await jobKeywords(id), id).toEqual(unavailable);
    expect(requests).toEqual([]);
  });

  test("route GET matches jobKeywords", async () => {
    const down = await closedPort();
    // [jobId(null이면 쿼리 없음), BACKEND_URL(undefined면 없음)]
    const rows: [string | null, string | undefined][] = [
      [null, backend],
      ["", backend],
      ["x".repeat(201), backend],
      ["dummy:backend-platform", backend],
      ["kr:1", backend],
      ["be:9001", backend],
      ["be:9002", backend],
      ["be:9003", backend],
      ["be:9004", backend],
      ["be:9005", backend],
      ["be:9999", backend],
      ["be:9001", undefined],
      ["be:9001", down],
    ];
    for (const [jobId, url] of rows) {
      if (url === undefined) delete process.env.BACKEND_URL;
      else process.env.BACKEND_URL = url;
      const label = `${jobId} @ ${url}`;
      const result = await jobKeywords(jobId ?? "");
      const query = jobId === null ? "" : `?jobId=${encodeURIComponent(jobId)}`;
      const response = await GET(
        new Request(`http://local/api/jobs/keywords${query}`),
      );
      expect(response.status, label).toBe(result.status);
      expect([...response.headers], label).toEqual([
        ["content-type", "application/json"],
      ]);
      expect(await response.text(), label).toBe(JSON.stringify(result.body));
    }
  });
});

test.describe("profile levels", () => {
  let profilePostingLevels: typeof ProfileLevels.profilePostingLevels;
  let jobKeywords: typeof JobKeywords.jobKeywords;
  let GET: typeof MyLevelsRoute.GET;
  let demoAccount: typeof DemoAccount.demoAccount;
  let server: Server;
  let backend: string;
  let loginHook: ReturnType<typeof registerHooks> | undefined;
  let fakeDir: string;
  let dataDir: string;
  let requests: string[] = [];
  let errors: ReturnType<typeof captureErrors>;

  const subject = "synthetic-subject";
  const version = "synthetic-v1";
  const contractLabels = [
    "2단계 규칙",
    "LLM 보충 끔",
    "제안 기준",
    "본인 확인 안 됨",
  ];
  // 이 시험이 바꾸는 환경 변수. 시험마다 처음 값으로 되돌린다.
  const envKeys = [
    "CAREER_DATA_DIR",
    "CAREER_PROFILE_NAMESPACE",
    "CAREER_PROFILE_DATABASE_URL",
    "CAREER_PROFILE_CA_FILE",
    "BACKEND_URL",
    "CAREER_LV_STAT",
  ] as const;
  const savedEnv: Partial<Record<(typeof envKeys)[number], string>> = {};
  // posting-levels.ts가 globalThis에 두는 RDS 연결. 시험이 만든 연결은 시험마다 닫는다.
  const pools = globalThis as unknown as {
    careerLevelPool?: { end(): Promise<void> };
  };

  // Spring /api/postings/{id}/skill-categories 모양의 합성 문장(분류됨, 카운트에 들어감, 검토 끝).
  const item = (
    itemId: number,
    text: string | null | undefined,
    categoryCodes: string[],
  ) => ({
    itemId,
    sourceCategory: "필수",
    text,
    assignment: {
      status: "CLASSIFIED",
      categoryCodes,
      excludedFromCounts: false,
      needsReview: false,
      relatedGroups: [],
    },
  });
  const posting = (
    items: ReturnType<typeof item>[],
    fields: Record<string, unknown> = { version },
  ) =>
    JSON.stringify({
      postingId: 1,
      ...fields,
      analysisStatus: "ANALYZED",
      recruitUnits: [{ unitId: 1, name: "합성 단위", items }],
    });
  // 작업 명세의 문장 3개: [B], [L, Java 문장], [Q]
  const briefItems = [
    item(1, "합성 서버 개발 경험", ["B"]),
    item(2, "Java 기반 합성 서비스 개발", ["L"]),
    item(3, "합성 코드 리뷰 경험", ["Q"]),
  ];
  // 경로 → [상태, 본문]. 없는 경로는 404(없는 공고)다.
  const answers: Record<string, [number, string]> = {
    "/api/postings/9101/skill-categories": [200, posting(briefItems)],
    "/api/postings/9102/skill-categories": [
      200,
      posting([
        item(11, "합성 데이터 모델링과 품질 관리", ["D", "Q", "D"]),
        item(12, "합성 보안 점검과 배포 운영", ["S", "O"]),
        item(13, "합성 데이터 파이프라인 운영", ["E"]),
        item(14, "합성 화면 개발", ["F"]),
        item(15, "합성 장비 연동", ["H"]),
      ]),
    ],
    "/api/postings/9103/skill-categories": [
      200,
      posting(briefItems, { version: null }),
    ],
    "/api/postings/9104/skill-categories": [200, posting(briefItems, {})],
    "/api/postings/9105/skill-categories": [
      200,
      posting([
        item(21, undefined, ["B"]),
        item(22, null, ["B"]),
        item(23, "합성 서버 운영", ["B"]),
      ]),
    ],
    "/api/postings/9106/skill-categories": [500, posting(briefItems)],
    "/api/postings/9107/skill-categories": [
      200,
      posting([item(31, "Java 기반 합성 서버 개발", ["B", "L"])]),
    ],
  };

  // 합성 분석 결과(CONTRACT 모양): B 2.0, D 3.0, O 1.5, E 0.0, F 판정 불가(null), A 0.0.
  // L은 Java 2.5·Python 3.5(가장 높은 언어 Python, L 3.5)라 Java 문장을 Java로 재면 50, L LV로 재면 70이다.
  function analyzed(subjectId = subject): LvProfile {
    const p = profile({ B: 2.0, D: 3.0, O: 1.5, F: null });
    return {
      ...p,
      subjectId,
      categories: {
        ...p.categories,
        L: {
          ...p.categories.L,
          lv: 3.5,
          languages: { Java: 2.5, Python: 3.5 },
          best: "Python",
        },
      },
    };
  }

  // 작업자처럼 profiles/<profileKey>.json에 결과를 둔다.
  const profileFile = (p: LvProfile) =>
    path.join(
      dataDir,
      "lv-stat",
      "profiles",
      `${contractKey(p.namespace, p.subjectId)}.json`,
    );
  async function store(p: LvProfile) {
    const file = profileFile(p);
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, JSON.stringify(p));
  }

  // 화면 행 하나. usedCodes는 점수를 낸 카테고리다. 비교 값 없음, 확정, 분석 시각(profile.analyzedAt)이다.
  const row = (
    keywordId: string,
    text: string,
    categoryCodes: string[],
    usedCodes: string[],
    score: number,
    evaluatedAt = "2026-11-28T00:00:00+09:00",
  ) => ({
    keywordId,
    text,
    categoryCodes,
    usedCodes,
    score,
    referenceScore: null,
    referenceKind: null,
    evaluationKind: "CONFIRMED",
    evaluatedAt,
  });
  const briefRows = [
    row("1", "합성 서버 개발 경험", ["B"], ["B"], 40),
    row("2", "Java 기반 합성 서비스 개발", ["L"], ["L"], 50),
  ];

  // my-levels route의 로그인 확인(store.ts의 user·isGuest)은 Next 요청 안에서만 쿠키를 읽는다. 그래서 이 시험에서는
  // 그 route가 읽는 store만 아래 시험용 로그인으로 바꾼다. 프로필 파일·가짜 백엔드·RDS 읽기는 진짜다.
  type Login = {
    user: { id: string; email: string; name: string } | null;
    guest?: string;
  };
  const login = (value: Login | undefined) => {
    (globalThis as { lvStatTestLogin?: Login }).lvStatTestLogin = value;
  };
  const member = (id: string) =>
    login({ user: { id, email: `${id}@example.invalid`, name: "합성 회원" } });

  async function myLevels(query: string) {
    const response = await GET(
      new Request(`http://local/api/jobs/my-levels?${query}`),
    );
    return {
      status: response.status,
      cacheControl: response.headers.get("cache-control"),
      body: await response.json(),
    };
  }
  const levelsFailure = {
    status: 502,
    cacheControl: "private, no-store",
    body: { error: "저장된 사용자 LV를 불러오지 못했습니다." },
  };
  const noSavedLevels = {
    status: 503,
    cacheControl: "private, no-store",
    body: { error: "사용자 LV 저장소 미연결" },
  };

  // RDS(저장된 LV)를 켜되 연결이 거부되는 곳을 준다. route가 RDS를 읽으면 오류(502)가 나서, 읽었는지 갈린다.
  // 돌려주는 값은 그 DB 주소(호스트:포트)다. 연결 오류의 글(message)에 들어간다.
  async function savedLevelsDown() {
    const url = `${(await closedPort()).replace("http://", "postgres://lv-test@")}/lv_test`;
    process.env.CAREER_PROFILE_DATABASE_URL = url;
    return new URL(url).host;
  }
  // my-levels route가 남긴 서버 기록. jobKeywords가 남기는 기록은 'job keywords' 시험이 본다.
  const routeLogs = () =>
    errors.calls.filter(([message]) => message === "My levels lookup failed");

  test.beforeAll(async () => {
    server = createServer((request, response) => {
      requests.push(request.url!);
      const [status, body] = answers[request.url!] ?? [404, "{}"];
      response
        .writeHead(status, { "Content-Type": "application/json" })
        .end(body);
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    backend = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    fakeDir = await mkdtemp(path.join(tmpdir(), "lv-stat-login-"));
    const fakeStore = path.join(fakeDir, "store.cjs");
    await writeFile(
      fakeStore,
      [
        "// 시험용 로그인: 시험이 globalThis.lvStatTestLogin에 넣은 사람이 로그인 사용자다.",
        "exports.user = async () => globalThis.lvStatTestLogin?.user ?? null;",
        "exports.isGuest = (id) => globalThis.lvStatTestLogin?.guest === id;",
      ].join("\n"),
    );
    loginHook = registerHooks({
      resolve: (specifier, context, nextResolve) =>
        nextResolve(
          specifier === "@/lib/server/store" &&
            context.parentURL?.endsWith("/app/api/jobs/my-levels/route.ts")
            ? fakeStore
            : specifier,
          context,
        ),
    });
    ({ jobKeywords } = await import("@/lib/server/job-keywords"));
    ({ profilePostingLevels } = await import("@/lib/server/profile-levels"));
    ({ GET } = await import("@/app/api/jobs/my-levels/route"));
    ({ demoAccount } = await import("@/lib/server/demo-account"));
  });

  test.afterAll(async () => {
    loginHook?.deregister();
    delete (globalThis as { lvStatTestLogin?: Login }).lvStatTestLogin;
    await rm(fakeDir, { recursive: true, force: true });
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  test.beforeEach(async () => {
    for (const key of envKeys) savedEnv[key] = process.env[key];
    dataDir = await mkdtemp(path.join(tmpdir(), "lv-stat-levels-"));
    process.env.CAREER_DATA_DIR = dataDir;
    process.env.CAREER_PROFILE_NAMESPACE = "staging";
    delete process.env.CAREER_PROFILE_DATABASE_URL;
    delete process.env.CAREER_PROFILE_CA_FILE;
    process.env.BACKEND_URL = backend;
    // 스테이징 웹처럼 스위치를 켠다. 꺼진 경우(운영)는 따로 시험한다.
    process.env.CAREER_LV_STAT = "on";
    requests = [];
    errors = captureErrors();
    login(undefined);
  });

  test.afterEach(async () => {
    errors.restore();
    login(undefined);
    await pools.careerLevelPool?.end();
    delete pools.careerLevelPool;
    for (const key of envKeys) {
      const value = savedEnv[key];
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    await rm(dataDir, { recursive: true, force: true });
  });

  test("rows computed from profile", async () => {
    await store(analyzed());
    // [B] → B 2.0 × 20 = 40, [L] Java 문장 → Java 2.5 × 20 = 50, [Q] → 점수 없음(행 없음)
    expect(
      (await profilePostingLevels(subject, "be:9101", version))?.levels,
    ).toEqual(briefRows);
    expect(requests).toEqual(["/api/postings/9101/skill-categories"]);
  });

  test("rows match page matching rule", async () => {
    await store(analyzed());
    const result = await profilePostingLevels(subject, "be:9102", version);
    // 같은 코드 두 번과 재지 않는 Q·S·H도 문장 그대로 둔다. 점수를 낸 카테고리(usedCodes)는 한 번씩이고 재는 것만이다.
    // 0점도 점수다. F(판정 불가)·H만 있는 문장은 행이 없다.
    expect(result?.levels).toEqual([
      row("11", "합성 데이터 모델링과 품질 관리", ["D", "Q", "D"], ["D"], 60),
      row("12", "합성 보안 점검과 배포 운영", ["S", "O"], ["O"], 30),
      row("13", "합성 데이터 파이프라인 운영", ["E"], ["E"], 0),
    ]);
    // 공고 화면(components/jobs/personal-job-comparison.tsx)은 /api/jobs/keywords로 받은 문장에
    // keywordId·text·정렬한 categoryCodes가 모두 같은 행만 쓴다. 행마다 맞는 문장이 하나다.
    const { body } = await jobKeywords("be:9102");
    const keywords = "keywords" in body ? body.keywords : [];
    for (const level of result!.levels)
      expect(
        keywords.filter(
          (keyword) =>
            keyword.id === level.keywordId &&
            keyword.text === level.text &&
            [...keyword.categoryCodes].sort().join() ===
              [...level.categoryCodes].sort().join(),
        ),
        level.keywordId,
      ).toHaveLength(1);
  });

  test("version mismatch returns no rows", async () => {
    await store(analyzed());
    // 화면이 물은 분류 버전과 공고 문장의 버전이 다르면 행이 없다. 문장 쪽 버전이 null이거나 없어도 같다.
    const rows: [string, string][] = [
      ["be:9101", "other-version"],
      ["be:9103", version],
      ["be:9104", version],
    ];
    for (const [jobId, asked] of rows)
      expect(
        await profilePostingLevels(subject, jobId, asked),
        jobId,
      ).toMatchObject({
        jobId,
        taxonomyVersion: asked,
        source: "LV_STAT",
        levels: [],
      });
  });

  test("no profile returns null", async () => {
    expect(await profilePostingLevels(subject, "be:9101", version)).toBeNull();
    // 다른 사람의 결과, 다른 namespace의 결과는 이 사람 것이 아니다.
    await store(analyzed("synthetic-other"));
    await store({ ...analyzed(), namespace: "other-namespace" });
    expect(await profilePostingLevels(subject, "be:9101", version)).toBeNull();
    // 결과가 없으면 공고 문장도 받지 않는다(그래서 백엔드가 실패해도 저장된 LV로 넘어갈 수 있다).
    expect(requests).toEqual([]);
    // namespace는 로그인 저장소와 같은 CAREER_PROFILE_NAMESPACE다.
    process.env.CAREER_PROFILE_NAMESPACE = "other-namespace";
    expect(
      await profilePostingLevels(subject, "be:9101", version),
    ).not.toBeNull();
  });

  test("labels and sources present", async () => {
    // 라벨·방식·아이디·분석 시각은 결과 파일 값을 그대로 쓴다(CONTRACT 값과 다른 합성 값으로 확인).
    await store({
      ...analyzed(),
      login: "synthetic-login",
      method: "synthetic-method-v9",
      labels: ["합성 라벨 1", "합성 라벨 2"],
      analyzedAt: "2026-11-27T12:34:56.000Z",
    });
    expect(await profilePostingLevels(subject, "be:9101", version)).toEqual({
      jobId: "be:9101",
      taxonomyVersion: version,
      source: "LV_STAT",
      levels: [
        row(
          "1",
          "합성 서버 개발 경험",
          ["B"],
          ["B"],
          40,
          "2026-11-27T12:34:56.000Z",
        ),
        row(
          "2",
          "Java 기반 합성 서비스 개발",
          ["L"],
          ["L"],
          50,
          "2026-11-27T12:34:56.000Z",
        ),
      ],
      sources: [
        {
          id: "lv-stat:synthetic-login",
          kind: "GITHUB",
          title: "synthetic-login",
          simulated: false,
        },
      ],
      labels: ["합성 라벨 1", "합성 라벨 2"],
      identityVerified: false,
      methodVersion: "synthetic-method-v9",
    });
  });

  test("posting that cannot be read throws", async () => {
    await store(analyzed());
    // 없는 공고(백엔드 404), 백엔드 오류(500), 문장 서버 연결 설정 없음(503)
    for (const jobId of ["be:9999", "be:9106"])
      await expect(
        profilePostingLevels(subject, jobId, version),
        jobId,
      ).rejects.toThrow();
    delete process.env.BACKEND_URL;
    await expect(
      profilePostingLevels(subject, "be:9101", version),
    ).rejects.toThrow();
  });

  test("keywords without text give no row", async () => {
    await store(analyzed());
    // 문장 글이 없거나(null) 빠진 문장은 화면이 행을 맞출 수 없다.
    expect(
      (await profilePostingLevels(subject, "be:9105", version))?.levels,
    ).toEqual([row("23", "합성 서버 운영", ["B"], ["B"], 40)]);
  });

  test("row names the categories that gave its score", async () => {
    // [B, L] Java 문장. B가 판정 불가(null)면 점수는 L(Java 2.5 × 20 = 50)에서만 나온다. categoryCodes는 화면이
    // 문장과 맞추는 키라 문장 그대로이고, 점수를 낸 카테고리는 usedCodes에 따로 있다(레이더가 그 축에만 값을 둔다).
    const p = analyzed();
    await store({
      ...p,
      categories: { ...p.categories, B: { ...p.categories.B, lv: null } },
    });
    expect(
      (await profilePostingLevels(subject, "be:9107", version))?.levels,
    ).toEqual([row("31", "Java 기반 합성 서버 개발", ["B", "L"], ["L"], 50)]);
    // B 2.0이 있으면 두 카테고리가 다 점수를 낸다: (2.0 + 2.5) ÷ 2 × 20 = 45
    await store(p);
    expect(
      (await profilePostingLevels(subject, "be:9107", version))?.levels,
    ).toEqual([
      row("31", "Java 기반 합성 서버 개발", ["B", "L"], ["B", "L"], 45),
    ]);
  });

  test("route reads the profile before saved levels", async () => {
    member(subject);
    await store(analyzed());
    // RDS가 켜져 있어도(연결 거부) 결과 파일이 있으면 RDS를 읽지 않는다.
    await savedLevelsDown();
    expect(await myLevels(`jobId=be:9101&version=${version}`)).toEqual({
      status: 200,
      cacheControl: "private, no-store",
      body: {
        jobId: "be:9101",
        taxonomyVersion: version,
        source: "LV_STAT",
        levels: briefRows,
        sources: [
          {
            id: "lv-stat:synthetic-user",
            kind: "GITHUB",
            title: "synthetic-user",
            simulated: false,
          },
        ],
        labels: contractLabels,
        identityVerified: false,
        methodVersion: "lv-stat-s2-20261127",
      },
    });
    // 성공하면 서버 기록이 없다.
    expect(errors.calls).toEqual([]);
  });

  test("route falls back to saved levels without a profile", async () => {
    member(subject);
    const asked = `jobId=be:9101&version=${version}`;
    // RDS 설정이 없으면 지금처럼 503
    expect(await myLevels(asked)).toEqual(noSavedLevels);
    // RDS를 읽다가 실패하면 지금처럼 502(결과 파일이 없을 때 RDS를 읽는다)
    await savedLevelsDown();
    expect(await myLevels(asked)).toEqual(levelsFailure);
    expect(requests).toEqual([]);
  });

  test("route takes the saved-levels path when the staging switch is off, even with a profile", async () => {
    // 스위치가 꺼진 웹(운영)은 결과 파일을 읽지 않고 지금처럼 저장된 LV(RDS)만 읽는다. 정확히 'on'일 때만 켜진다.
    member(subject);
    await store(analyzed());
    const asked = `jobId=be:9101&version=${version}`;
    for (const value of [undefined, "", "off", "ON", "true"]) {
      if (value === undefined) delete process.env.CAREER_LV_STAT;
      else process.env.CAREER_LV_STAT = value;
      // RDS 설정이 없으면 503이다(결과 파일로 계산했다면 200이다).
      expect(await myLevels(asked), String(value)).toEqual(noSavedLevels);
    }
    // RDS를 읽다 실패하면 502다: 결과 파일 대신 RDS를 읽었다.
    await savedLevelsDown();
    expect(await myLevels(asked)).toEqual(levelsFailure);
    // 결과 파일로 계산하지 않으니 공고 문장도 받지 않는다.
    expect(requests).toEqual([]);
    // 켜면 같은 회원·같은 결과 파일로 계산한다(RDS가 연결 거부여도 읽지 않는다).
    process.env.CAREER_LV_STAT = "on";
    expect(await myLevels(asked)).toMatchObject({
      status: 200,
      body: { source: "LV_STAT", levels: briefRows },
    });
  });

  test("route reads only the session user's profile", async () => {
    member(subject);
    await store(analyzed("synthetic-other"));
    // 주소에 다른 사람 id를 넣어도 로그인한 사람의 결과만 읽는다(이 사람은 결과가 없어 RDS로 간다).
    expect(
      await myLevels(
        `jobId=be:9101&version=${version}&userId=synthetic-other&subjectId=synthetic-other&subject=synthetic-other`,
      ),
    ).toEqual(noSavedLevels);
    expect(requests).toEqual([]);
  });

  test("route answers 502 when the posting cannot be read", async () => {
    member(subject);
    await store(analyzed());
    // 없는 공고(백엔드 404), 백엔드 오류(500), 문장 서버 연결 설정 없음(503)
    for (const jobId of ["be:9999", "be:9106"])
      expect(
        await myLevels(`jobId=${jobId}&version=${version}`),
        jobId,
      ).toEqual(levelsFailure);
    delete process.env.BACKEND_URL;
    expect(await myLevels(`jobId=be:9101&version=${version}`)).toEqual(
      levelsFailure,
    );
    // route는 공고 문장 응답의 상태를 남긴다. 백엔드가 실패한 이유는 jobKeywords가 따로 남긴다.
    expect(routeLogs()).toEqual([
      [
        "My levels lookup failed",
        { jobId: "be:9999", error: "Error: 공고 문장 응답 502" },
      ],
      [
        "My levels lookup failed",
        { jobId: "be:9106", error: "Error: 공고 문장 응답 502" },
      ],
      [
        "My levels lookup failed",
        { jobId: "be:9101", error: "Error: 공고 문장 응답 503" },
      ],
    ]);
  });

  test("route logs a profile it cannot read without the file path", async () => {
    member(subject);
    const asked = `jobId=be:9101&version=${version}`;
    const file = profileFile(analyzed());
    // 결과 파일 자리가 폴더다(EISDIR).
    await mkdir(file, { recursive: true });
    expect(await myLevels(asked)).toEqual(levelsFailure);
    // 결과 파일을 읽을 권한이 없다(EACCES). 이 오류의 글(message)에는 결과 파일 경로가 있다.
    await rm(file, { recursive: true });
    await store(analyzed());
    await chmod(file, 0o000);
    expect(await myLevels(asked)).toEqual(levelsFailure);
    // 기록은 오류 이름만 남긴다. 공고 문장은 받지 않았다.
    expect(errors.calls).toEqual([
      ["My levels lookup failed", { jobId: "be:9101", error: "Error" }],
      ["My levels lookup failed", { jobId: "be:9101", error: "Error" }],
    ]);
    const logged = JSON.stringify(errors.calls);
    for (const leak of [
      dataDir,
      contractKey("staging", subject),
      "EISDIR",
      "EACCES",
    ])
      expect(logged, leak).not.toContain(leak);
    expect(requests).toEqual([]);
  });

  test("route logs a saved-levels failure without the database address", async () => {
    member(subject);
    const database = await savedLevelsDown();
    expect(await myLevels(`jobId=be:9101&version=${version}`)).toEqual(
      levelsFailure,
    );
    // 연결 오류의 글(message)에는 DB 주소가 있어 이름만 남긴다.
    expect(errors.calls).toEqual([
      ["My levels lookup failed", { jobId: "be:9101", error: "Error" }],
    ]);
    const logged = JSON.stringify(errors.calls);
    for (const leak of [database, "lv-test", "ECONNREFUSED"])
      expect(logged, leak).not.toContain(leak);
  });

  test("route gives the demo account saved levels even with a profile", async () => {
    // 데모 계정은 로그인 화면의 '데모 계정으로 로그인'으로 누구나 같이 쓴다. 그 계정의 결과 파일이 있어도 읽지 않고
    // 지금처럼 저장된 LV(RDS의 DEMO 행)를 읽는다. 분석 결과는 요청한 사람에게만 보인다.
    await store(analyzed("demo-user"));
    login({
      user: {
        id: "demo-user",
        email: demoAccount.email,
        name: demoAccount.name,
      },
    });
    const asked = `jobId=be:9101&version=${version}`;
    // RDS 설정이 없으면 503, RDS를 읽다 실패하면 502다. 결과 파일로 계산하지 않으니 공고 문장도 받지 않는다.
    expect(await myLevels(asked)).toEqual(noSavedLevels);
    await savedLevelsDown();
    expect(await myLevels(asked)).toEqual(levelsFailure);
    expect(requests).toEqual([]);
    // 같은 id라도 데모 이메일이 아닌 회원은 그 결과 파일로 계산한다(읽을 수 있는 결과 파일이다).
    member("demo-user");
    expect(await myLevels(asked)).toMatchObject({
      status: 200,
      body: { source: "LV_STAT", levels: briefRows },
    });
  });

  test("route checks login and input before reading a profile", async () => {
    await store(analyzed());
    await store(analyzed("synthetic-guest"));
    const asked = `jobId=be:9101&version=${version}`;
    const unauthorized = {
      status: 401,
      cacheControl: "private, no-store",
      body: { error: "로그인이 필요합니다." },
    };
    // 로그인 안 함, 손님(결과 파일이 있어도)
    expect(await myLevels(asked)).toEqual(unauthorized);
    login({
      user: {
        id: "synthetic-guest",
        email: "synthetic-guest@example.invalid",
        name: "손님",
      },
      guest: "synthetic-guest",
    });
    expect(await myLevels(asked)).toEqual(unauthorized);
    // 분류 버전이 없는 요청
    member(subject);
    expect(await myLevels("jobId=be:9101")).toEqual({
      status: 400,
      cacheControl: "private, no-store",
      body: { error: "공고와 분류 버전을 확인해 주세요." },
    });
    expect(requests).toEqual([]);
  });
});

// app/api/lv-stat/analysis/route.ts의 POST·GET을 직접 부른다. 같은 확인을 dev 서버로 하는 e2e
// (tests/lv-stat-analysis.spec.ts)는 CI가 돌리지 않아서, 서버 쪽 규칙을 CI가 돌리는 이 계약 시험에도 둔다.
test.describe("analysis api", () => {
  let GET: typeof AnalysisRoute.GET;
  let POST: typeof AnalysisRoute.POST;
  let realStore: typeof Store;
  let demoAccount: typeof DemoAccount.demoAccount;
  let loginHook: ReturnType<typeof registerHooks> | undefined;
  let fakeDir: string;
  let dataDir: string;
  let errors: ReturnType<typeof captureErrors>;

  const namespace = "staging";
  const signIn = "로그인이 필요합니다.";
  const badOrigin = "요청 출처를 확인할 수 없습니다.";
  const urlHelp =
    "GitHub 계정 주소를 넣어 주세요. 예: https://github.com/아이디";
  const demoRefused = "데모 계정은 GitHub 분석을 할 수 없어요.";
  const busy = "이미 분석 중이에요. 끝나면 다시 시도해 주세요.";
  const full = "지금 분석 요청이 많아요. 잠시 뒤 다시 시도해 주세요.";
  const requestFailed = "분석 요청을 처리하지 못했어요.";
  const lookupFailed = "분석 결과를 불러오지 못했어요.";
  const switchedOff = "GitHub 분석을 쓸 수 없어요.";
  const uuidV4 =
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  // 이 시험이 바꾸는 환경 변수. 시험마다 처음 값으로 되돌린다.
  const envKeys = [
    "CAREER_DATA_DIR",
    "CAREER_PROFILE_NAMESPACE",
    "CAREER_LV_STAT",
  ] as const;
  const savedEnv: Partial<Record<(typeof envKeys)[number], string>> = {};

  // route의 store(@/lib/server/store)만 시험용으로 바꾼다. store.ts의 user·isGuest는 Next 요청 안에서만 쿠키를
  // 읽고 rateLimit은 SQLite를 쓰기 때문이다. 로그인 사용자·손님 id·rateLimit이 던질 것은 시험이 정하고,
  // originCheck·jsonBody는 진짜 store.ts 함수를 부른다. route가 부른 store 함수와 인자는 calls에 순서대로 쌓인다.
  // 요청·결과 파일(lib/server/lv-stat.ts)은 진짜이고, 시험마다 새 CAREER_DATA_DIR에 쓴다.
  type Account = { id: string; email: string; name: string };
  type Double = {
    user: Account | null;
    guest?: string;
    limitError?: unknown;
    calls: unknown[][];
    originCheck: (req: Request) => void;
    jsonBody: (req: Request) => Promise<unknown>;
  };
  let double: Double;
  const as = (user: Account | null, guest?: string) => {
    double.user = user;
    double.guest = guest;
  };
  const member = (id: string) =>
    as({ id, email: `${id}@example.invalid`, name: "합성 회원" });
  const guest = (id: string) =>
    as({ id, email: `${id}@example.invalid`, name: "손님" }, id);
  const demo = () =>
    as({ id: "demo-user", email: demoAccount.email, name: demoAccount.name });
  // 지금까지 쌓인 store 부름을 꺼내고 비운다.
  const took = () => double.calls.splice(0);
  // 회원의 POST가 지나는 store 부름: 출처 → 로그인 → 손님 확인 → rateLimit(키 lv-stat:<id>, 최대 6) → 본문
  const memberCalls = (id: string) => [
    ["originCheck"],
    ["user"],
    ["isGuest", id],
    ["rateLimit", `lv-stat:${id}`, 6],
    ["jsonBody"],
  ];

  const sameSite = { origin: "http://local", host: "local" };
  async function answer(response: Response) {
    return {
      status: response.status,
      cacheControl: response.headers.get("cache-control"),
      body: await response.json(),
    };
  }
  // body가 글이면 그대로 보내고(JSON 아닌 본문), 아니면 JSON으로 보낸다.
  async function post(
    body: unknown,
    headers: Record<string, string> = sameSite,
  ) {
    return answer(
      await POST(
        new Request("http://local/api/lv-stat/analysis", {
          method: "POST",
          headers: { "content-type": "application/json", ...headers },
          body: typeof body === "string" ? body : JSON.stringify(body),
        }),
      ),
    );
  }
  const get = async () => answer(await GET());
  const refused = (status: number, error: string) => ({
    status,
    cacheControl: "private, no-store",
    body: { error },
  });
  const found = (job: LvJob | null, profile: LvProfile | null = null) => ({
    status: 200,
    cacheControl: "private, no-store",
    body: { job, profile },
  });
  // 회원의 POST가 202이고 그 job을 준다.
  async function queued(url = "https://github.com/synthetic-user") {
    const { status, body } = await post({ url });
    expect(status, url).toBe(202);
    return body.job as LvJob;
  }

  const jobsDir = () => path.join(dataDir, "lv-stat", "jobs");
  const jobPath = (id: string) => path.join(jobsDir(), `${id}.json`);
  const profilePath = (subjectId: string) =>
    path.join(
      dataDir,
      "lv-stat",
      "profiles",
      `${contractKey(namespace, subjectId)}.json`,
    );
  async function jobFiles() {
    try {
      return (await readdir(jobsDir())).sort();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }
  }
  async function writeJson(file: string, value: unknown) {
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, JSON.stringify(value));
  }
  const resultOf = (subjectId: string, jobId: string): LvProfile => ({
    ...profile({ B: 2.0 }),
    subjectId,
    jobId,
  });
  // 작업자가 끝낸 요청 파일과 그 결과 파일(CONTRACT 모양)을 둔다.
  async function finished(subjectId: string) {
    const job: LvJob = {
      id: "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b",
      namespace,
      subjectId,
      login: "synthetic-user",
      input: "https://github.com/synthetic-user",
      status: "done",
      createdAt: "2026-11-28T00:00:00.000Z",
      stage: "끝",
      progress: { done: 1, total: 1 },
      startedAt: "2026-11-28T00:00:01.000Z",
      finishedAt: "2026-11-28T00:01:00.000Z",
      profileKey: contractKey(namespace, subjectId),
    };
    const result = resultOf(subjectId, job.id);
    await writeJson(jobPath(job.id), job);
    await writeJson(profilePath(subjectId), result);
    return { job, profile: result };
  }

  // 진짜 store.ts rateLimit이 최대 6일 때 7번째 부름에서 던지는 글. 이 시험의 dataDir에 새 SQLite를 열어 재고 닫는다.
  function storeLimitMessage() {
    const shared = globalThis as unknown as { careerDb?: { close(): void } };
    const previous = shared.careerDb;
    // store.ts db()가 globalThis에 둔 연결을 비워 새 dataDir에 새로 열게 한다. delete를 쓰면 TS가 아래
    // finally에서 careerDb를 없는 값으로 좁혀서 Reflect로 지운다.
    Reflect.deleteProperty(shared, "careerDb");
    try {
      for (let i = 0; i < 6; i++) realStore.rateLimit("lv-stat:limit-probe", 6);
      try {
        realStore.rateLimit("lv-stat:limit-probe", 6);
      } catch (error) {
        return (error as Error).message;
      }
      throw new Error("store.ts rateLimit allowed a 7th call with max 6");
    } finally {
      shared.careerDb?.close();
      if (previous) shared.careerDb = previous;
      else delete shared.careerDb;
    }
  }

  test.beforeAll(async () => {
    fakeDir = await mkdtemp(path.join(tmpdir(), "lv-stat-analysis-login-"));
    const fakeStore = path.join(fakeDir, "store.cjs");
    await writeFile(
      fakeStore,
      [
        "// 시험용 store: 시험이 globalThis.lvStatAnalysisTest에 둔 값으로 답하고, 부른 함수와 인자를 calls에 남긴다.",
        "const t = () => globalThis.lvStatAnalysisTest;",
        "const called = (...call) => t().calls.push(call);",
        "exports.originCheck = (req) => { called('originCheck'); t().originCheck(req); };",
        "exports.user = async () => { called('user'); return t().user; };",
        "exports.isGuest = (id) => { called('isGuest', id); return t().guest === id; };",
        "exports.rateLimit = (key, max) => { called('rateLimit', key, max); if (t().limitError !== undefined) throw t().limitError; };",
        "exports.jsonBody = (req) => { called('jsonBody'); return t().jsonBody(req); };",
      ].join("\n"),
    );
    loginHook = registerHooks({
      resolve: (specifier, context, nextResolve) =>
        nextResolve(
          specifier === "@/lib/server/store" &&
            context.parentURL?.endsWith("/app/api/lv-stat/analysis/route.ts")
            ? fakeStore
            : specifier,
          context,
        ),
    });
    realStore = await import("@/lib/server/store");
    ({ demoAccount } = await import("@/lib/server/demo-account"));
    ({ GET, POST } = await import("@/app/api/lv-stat/analysis/route"));
  });

  test.afterAll(async () => {
    loginHook?.deregister();
    await rm(fakeDir, { recursive: true, force: true });
  });

  test.beforeEach(async () => {
    for (const key of envKeys) savedEnv[key] = process.env[key];
    dataDir = await mkdtemp(path.join(tmpdir(), "lv-stat-analysis-"));
    process.env.CAREER_DATA_DIR = dataDir;
    process.env.CAREER_PROFILE_NAMESPACE = namespace;
    // 스테이징 웹처럼 스위치를 켠다. 꺼진 경우(운영)는 따로 시험한다.
    process.env.CAREER_LV_STAT = "on";
    double = {
      user: null,
      calls: [],
      originCheck: realStore.originCheck,
      jsonBody: realStore.jsonBody,
    };
    (globalThis as { lvStatAnalysisTest?: Double }).lvStatAnalysisTest = double;
    errors = captureErrors();
  });

  test.afterEach(async () => {
    errors.restore();
    delete (globalThis as { lvStatAnalysisTest?: Double }).lvStatAnalysisTest;
    for (const key of envKeys) {
      const value = savedEnv[key];
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    await rm(dataDir, { recursive: true, force: true });
  });

  test("signed-out visitors and guests get 401 on POST and GET", async () => {
    // 손님 id의 요청·결과 파일이 있어도 401이다.
    await finished("synthetic-guest");
    const before = await jobFiles();
    const input = { url: "https://github.com/synthetic-user" };
    as(null);
    expect(await post(input)).toEqual(refused(401, signIn));
    expect(took()).toEqual([["originCheck"], ["user"]]);
    expect(await get()).toEqual(refused(401, signIn));
    expect(took()).toEqual([["user"]]);
    guest("synthetic-guest");
    expect(await post(input)).toEqual(refused(401, signIn));
    expect(took()).toEqual([
      ["originCheck"],
      ["user"],
      ["isGuest", "synthetic-guest"],
    ]);
    expect(await get()).toEqual(refused(401, signIn));
    expect(took()).toEqual([["user"], ["isGuest", "synthetic-guest"]]);
    // rateLimit·본문 읽기 전에 막아 요청 파일이 늘지 않는다.
    expect(await jobFiles()).toEqual(before);
    expect(errors.calls).toEqual([]);
  });

  test("with the staging switch off, POST and GET are 404 before the session or any file is read", async () => {
    // 스테이징 웹 유닛만 CAREER_LV_STAT=on이다(deploy/web/deploy.sh). 정확히 'on'이 아니면 모두 꺼짐이다.
    member("member-a");
    const input = { url: "https://github.com/synthetic-user" };
    const offValues = [undefined, "", "off", "ON", "On", "true", "1", " on"];
    for (const value of offValues) {
      if (value === undefined) delete process.env.CAREER_LV_STAT;
      else process.env.CAREER_LV_STAT = value;
      const label = JSON.stringify(value ?? null);
      expect(await post(input), label).toEqual(refused(404, switchedOff));
      expect(await get(), label).toEqual(refused(404, switchedOff));
      // 출처·로그인·rateLimit·본문을 보지 않고, 데이터 폴더에 아무것도 만들지 않는다.
      expect(took(), label).toEqual([]);
      expect(await readdir(dataDir), label).toEqual([]);
    }
    // 읽으면 실패하는 요청 파일(권한 없음)과 결과 자리(폴더)가 있어도 404다.
    process.env.CAREER_LV_STAT = "off";
    const planted = await finished("member-a");
    await chmod(jobPath(planted.job.id), 0o000);
    await rm(profilePath("member-a"));
    await mkdir(profilePath("member-a"));
    expect(await get()).toEqual(refused(404, switchedOff));
    expect(await post(input)).toEqual(refused(404, switchedOff));
    expect(took()).toEqual([]);
    expect(await jobFiles()).toEqual([`${planted.job.id}.json`]);
    expect(errors.calls).toEqual([]);
    // 켜면 같은 회원의 GET이 그 파일을 읽다가 실패한다(500). 위의 404는 파일을 읽지 않은 것이다.
    process.env.CAREER_LV_STAT = "on";
    expect(await get()).toEqual(refused(500, lookupFailed));
    expect(took()).toEqual([["user"], ["isGuest", "member-a"]]);
    expect(errors.calls).toEqual([
      ["LV analysis lookup failed", { error: "Error" }],
    ]);
  });

  test("a POST from another site, without an origin, or with origin null is 403", async () => {
    member("member-a");
    const input = { url: "https://github.com/synthetic-user" };
    const origins: Record<string, string>[] = [
      { origin: "https://untrusted.example", host: "local" },
      { host: "local" },
      { origin: "null", host: "local" },
    ];
    for (const headers of origins) {
      expect(await post(input, headers), JSON.stringify(headers)).toEqual(
        refused(403, badOrigin),
      );
      // 출처를 가장 먼저 본다: 로그인·rateLimit·본문을 보지 않는다.
      expect(took()).toEqual([["originCheck"]]);
    }
    // 진짜 originCheck가 던지는 것. 다른 사이트·출처 없음은 store.ts의 글이고, Origin: null은 주소가 아니라
    // TypeError('Invalid URL')다. route는 셋 다 store.ts의 글로 답한다.
    const realCheck = (headers: Record<string, string>) => {
      try {
        realStore.originCheck(new Request("http://local/", { headers }));
      } catch (error) {
        return error instanceof Error
          ? `${error.name}: ${error.message}`
          : String(error);
      }
      return "passed";
    };
    expect(origins.map(realCheck)).toEqual([
      `Error: ${badOrigin}`,
      `Error: ${badOrigin}`,
      "TypeError: Invalid URL",
    ]);
    expect(realCheck(sameSite)).toBe("passed");
    expect(await jobFiles()).toEqual([]);
    expect(await get()).toEqual(found(null));
    expect(errors.calls).toEqual([]);
  });

  test("the demo account gets 403 on POST and nothing is written", async () => {
    demo();
    expect(await post({ url: "https://github.com/synthetic-user" })).toEqual(
      refused(403, demoRefused),
    );
    // rateLimit·본문 앞에서 막아 데이터 폴더에 아무것도 생기지 않는다.
    expect(took()).toEqual([
      ["originCheck"],
      ["user"],
      ["isGuest", "demo-user"],
    ]);
    expect(await readdir(dataDir)).toEqual([]);
    // 같은 id라도 데모 이메일이 아닌 회원은 요청할 수 있다(데모는 이메일로 가른다).
    member("demo-user");
    expect(await queued()).toMatchObject({ subjectId: "demo-user" });
    expect(errors.calls).toEqual([]);
  });

  test("GET for the demo account gives nulls without reading any file", async () => {
    const planted = await finished("demo-user");
    demo();
    expect(await get()).toEqual(found(null));
    // 같은 id의 보통 회원에게는 두 파일이 보인다(route가 데모 계정으로 읽었다면 받았을 값이다).
    member("demo-user");
    expect(await get()).toEqual(found(planted.job, planted.profile));
    // 두 파일을 모두 읽을 수 없게 한다: 요청 파일은 권한 없음(EACCES), 결과 자리는 폴더(EISDIR).
    // 어느 하나라도 읽으면 500이므로, 데모 GET이 200이면 아무 파일도 읽지 않은 것이다.
    await chmod(jobPath(planted.job.id), 0o000);
    await rm(profilePath("demo-user"));
    await mkdir(profilePath("demo-user"));
    demo();
    expect(await get()).toEqual(found(null));
    member("demo-user");
    expect(await get()).toEqual(refused(500, lookupFailed));
    expect(errors.calls).toEqual([
      ["LV analysis lookup failed", { error: "Error" }],
    ]);
  });

  test("the rate limit gives 429 with the store's message before the body is read", async () => {
    // route는 rateLimit이 던진 글을 store.ts의 한도 글과 맞춰 429로 바꾼다. 그 글은 진짜 store.ts에서 잰다.
    const limited = storeLimitMessage();
    member("member-a");
    double.limitError = new Error(limited);
    expect(await post({ url: "https://github.com/synthetic-user" })).toEqual(
      refused(429, limited),
    );
    // 키는 회원마다(lv-stat:<id>), 최대 6이다. 본문을 읽지 않고 요청 파일도 만들지 않는다.
    expect(took()).toEqual(memberCalls("member-a").slice(0, 4));
    expect(await jobFiles()).toEqual([]);
    expect(errors.calls).toEqual([]);
  });

  test("an address that is not a GitHub account gets 400 with an example", async () => {
    member("member-a");
    const bodies: unknown[] = [
      { url: "https://gitlab.com/synthetic-user" },
      { url: "github.com/synthetic-user" },
      { url: "https://github.com/synthetic user" },
      { url: "https://github.com/synthetic-user/repo/tree/main" },
      { url: " \t\n " },
      {},
      { url: 42 },
      { url: ["https://github.com/synthetic-user"] },
      "null",
      // JSON이 아닌 본문, 빈 본문
      "https://github.com/synthetic-user",
      "",
    ];
    for (const body of bodies) {
      expect(await post(body), JSON.stringify(body)).toEqual(
        refused(400, urlHelp),
      );
      expect(took(), JSON.stringify(body)).toEqual(memberCalls("member-a"));
    }
    expect(await jobFiles()).toEqual([]);
    expect(await get()).toEqual(found(null));
    expect(errors.calls).toEqual([]);
  });

  test("a member's POST is 202 with the trimmed address, and GET returns the same job", async () => {
    member("member-a");
    const start = Date.now();
    const created = await post({
      url: " \n\thttps://github.com/Synthetic-User/sample-repo/\t ",
    });
    expect(created).toEqual({
      status: 202,
      cacheControl: "private, no-store",
      body: {
        job: {
          id: expect.stringMatching(uuidV4),
          namespace,
          subjectId: "member-a",
          login: "Synthetic-User",
          input: "https://github.com/Synthetic-User/sample-repo/",
          status: "queued",
          createdAt: expect.any(String),
        },
      },
    });
    const job = created.body.job as LvJob;
    expect(Date.parse(job.createdAt)).toBeGreaterThanOrEqual(start);
    expect(Date.parse(job.createdAt)).toBeLessThanOrEqual(Date.now());
    expect(took()).toEqual(memberCalls("member-a"));
    // 요청 파일은 그 job 하나이고, 파일에 저장된 주소도 앞뒤 공백을 뺀 것이다.
    expect(await jobFiles()).toEqual([`${job.id}.json`]);
    expect(JSON.parse(await readFile(jobPath(job.id), "utf8"))).toEqual(job);
    expect(await get()).toEqual(found(job));
    expect(took()).toEqual([["user"], ["isGuest", "member-a"]]);
    // 작업자가 결과 파일을 쓰면 GET이 그 결과도 준다.
    const result = resultOf("member-a", job.id);
    await writeJson(profilePath("member-a"), result);
    expect(await get()).toEqual(found(job, result));
    expect(errors.calls).toEqual([]);
  });

  test("a second POST while the first is queued is 409", async () => {
    member("member-a");
    const first = await queued();
    expect(await post({ url: "https://github.com/synthetic-other" })).toEqual(
      refused(409, busy),
    );
    expect(await jobFiles()).toEqual([`${first.id}.json`]);
    expect(await get()).toEqual(found(first));
    expect(errors.calls).toEqual([]);
  });

  test("a POST at the queue cap of 20 is 503", async () => {
    for (let i = 1; i <= 20; i++) {
      member(`member-${i}`);
      await queued();
    }
    member("member-21");
    expect(await post({ url: "https://github.com/synthetic-user" })).toEqual(
      refused(503, full),
    );
    expect(await jobFiles()).toHaveLength(20);
    expect(await get()).toEqual(found(null));
    expect(errors.calls).toEqual([]);
  });

  test("GET by another member shows none of the first member's job or profile", async () => {
    member("member-a");
    const jobA = await queued();
    const resultA = resultOf("member-a", jobA.id);
    await writeJson(profilePath("member-a"), resultA);
    member("member-b");
    expect(await get()).toEqual(found(null));
    // B의 요청은 A의 진행 중 요청에 막히지 않고 B 것으로 만들어진다.
    const jobB = await queued("https://github.com/synthetic-other");
    expect(jobB).toMatchObject({
      subjectId: "member-b",
      login: "synthetic-other",
    });
    expect(await get()).toEqual(found(jobB));
    member("member-a");
    expect(await get()).toEqual(found(jobA, resultA));
    expect(errors.calls).toEqual([]);
  });

  test("an unexpected error is 500 and the log has the error name only", async () => {
    member("member-a");
    const input = "https://github.com/Synthetic-Login/synthetic-repo";
    // 요청 폴더에 읽을 수 없는 요청 파일(EACCES)이 있다. 이 오류의 글(message)에는 그 파일 경로가 있다.
    const planted = await finished("member-z");
    await chmod(jobPath(planted.job.id), 0o000);
    expect(await post({ url: input })).toEqual(refused(500, requestFailed));
    expect(await get()).toEqual(refused(500, lookupFailed));
    // rateLimit이 한도가 아닌 것(DB 등)으로 실패하면 429가 아니라 500이다. Error가 아닌 것을 던져도 같다.
    const database = path.join(dataDir, "career.sqlite");
    double.limitError = new Error(`unable to open database file ${database}`);
    expect(await post({ url: input })).toEqual(refused(500, requestFailed));
    double.limitError = "synthetic failure";
    expect(await post({ url: input })).toEqual(refused(500, requestFailed));
    // 기록은 오류 이름만 남긴다: 경로·파일 이름·오류 코드·넣은 주소·아이디·회원 id가 없다.
    expect(errors.calls).toEqual([
      ["LV analysis request failed", { error: "Error" }],
      ["LV analysis lookup failed", { error: "Error" }],
      ["LV analysis request failed", { error: "Error" }],
      ["LV analysis request failed", { error: "UnknownError" }],
    ]);
    const logged = JSON.stringify(errors.calls);
    for (const leak of [
      dataDir,
      planted.job.id,
      "EACCES",
      "career.sqlite",
      "synthetic failure",
      input,
      "Synthetic-Login",
      "member-a",
    ])
      expect(logged, leak).not.toContain(leak);
    expect(await jobFiles()).toEqual([`${planted.job.id}.json`]);
  });
});
