import type { LvCategoryCode, LvProfile } from "@/types/lv-stat";

// 이 서비스가 재는 카테고리(CONTRACT.md). 팀 코드 Q·S·H와 보조 코드는 점수에 넣지 않는다.
const scoredCodes: ReadonlySet<string> = new Set<LvCategoryCode>([
  "L",
  "B",
  "D",
  "E",
  "O",
  "F",
  "A",
]);

// 「Claude 임시값」: 공고 문장에서 언어를 찾는 사전. 이름은 GitHub Linguist 이름(프로필 languages 키),
// 순서는 CONTRACT.md 언어 목록 순서다. Objective-C는 C와 가르려고 더했다.
// - 영문 이름은 앞뒤에 영문·숫자·_가 붙지 않은 낱말만 센다. Go·C 말고는 뒤에 붙은 판 번호(Java8·PHP7)도 센다.
// - 한글 이름은 조사가 바로 붙으므로 경계를 보지 않는다.
// - Go·C는 흔한 낱말(go to market)과 겹치지 않게 대소문자를 가린다. C는 B2C처럼 영문·숫자에 붙은 것,
//   앞에 '-'가 붙은 것(Objective-C), 뒤에 #·+가 붙은 것(C#·C++)을 C로 세지 않는다.
// - SQL은 데이터베이스(D) 몫이라 넣지 않았다. JS·TS 같은 줄임말은 Node.js 같은 이름과 겹쳐 넣지 않았다.
type LanguagePattern = readonly [name: string, pattern: RegExp];
const languagePatterns: readonly LanguagePattern[] = [
  ["Java", /\bjava\d*\b(?!\s?script)|자바(?!\s?스크립트)/i],
  ["Kotlin", /\bkotlin\d*\b|코틀린/i],
  ["Python", /\bpython\d*\b|파이썬/i],
  ["JavaScript", /\bjava\s?script\d*\b|자바\s?스크립트/i],
  ["TypeScript", /\btypescript\d*\b|타입스크립트/i],
  ["Go", /\bGo\b|\b[Gg]o[Ll]ang\b/],
  ["C", /(?<![\w-])C(?![\w#+])/],
  ["C++", /(?<![\w-])C\+\+/i],
  ["C#", /(?<![\w-])C#/i],
  ["Swift", /\bswift\d*\b/i],
  ["Dart", /\bdart\d*\b/i],
  ["Ruby", /\bruby\d*\b/i],
  ["PHP", /\bphp\d*\b/i],
  ["Rust", /\brust\d*\b/i],
  ["Scala", /\bscala\d*\b/i],
  ["Objective-C", /\bobjective-c\b/i],
];

// 공고 문장에 적힌 언어(Linguist 이름, 사전 순서, 중복 없음).
export function detectLanguages(text: string): string[] {
  return languagePatterns
    .filter(([, pattern]) => pattern.test(text))
    .map(([name]) => name);
}

// 공고 문장 하나의 점수(CONTRACT.md '공고 문장 점수'). 문장 카테고리 중 이 서비스가 재고 LV가 있는 것만
// 쓰고(used), 남는 것이 없으면 점수 없음(null). 점수는 값들의 평균 × 20을 반올림한 0~100 정수다.
export function scoreKeyword(
  profile: LvProfile,
  keyword: { text: string; categoryCodes: string[] },
): { score: number | null; used: LvCategoryCode[] } {
  const used: LvCategoryCode[] = [];
  let tenths = 0;
  for (const code of new Set(keyword.categoryCodes)) {
    if (!isScored(code)) continue;
    const lv = profile.categories[code].lv;
    if (lv === null) continue;
    used.push(code);
    const value =
      code === "L" ? programmingValue(profile, keyword.text, lv) : lv;
    tenths += Math.round(value * 10);
  }
  if (!used.length) return { score: null, used };
  // LV는 소수 첫째 자리라 0.1 단위 정수로 더한다. 평균 × 20 = 그 합 × 2 ÷ 개수라 x.5가 그대로 남아,
  // 부동소수 오차(23.4999…)로 내림되지 않고 올림된다.
  const score = Math.round((tenths * 2) / used.length);
  return { score: Math.min(100, Math.max(0, score)), used };
}

function isScored(code: string): code is LvCategoryCode {
  return scoredCodes.has(code);
}

// L: 문장에 적힌 언어가 있으면 그 언어 LV 중 가장 높은 것(안 쓴 언어는 0), 없으면 L LV.
function programmingValue(profile: LvProfile, text: string, lv: number) {
  const named = detectLanguages(text);
  if (!named.length) return lv;
  return Math.max(
    ...named.map((name) => profile.categories.L.languages[name] ?? 0),
  );
}
