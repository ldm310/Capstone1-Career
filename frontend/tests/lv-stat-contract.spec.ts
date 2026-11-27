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
