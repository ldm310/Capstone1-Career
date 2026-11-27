import { test, expect } from "@playwright/test";
import { detectLanguages, scoreKeyword } from "@/lib/lv-stat/score";
import type { LvCategory, LvCategoryCode, LvProfile } from "@/types/lv-stat";

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
