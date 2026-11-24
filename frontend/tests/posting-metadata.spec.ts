import { test, expect } from "@playwright/test";
import { parsePostingMetadata } from "../lib/server/posting-metadata";
test("stored HTML yields explicit metadata without treating image-only or negative remote statements as facts", () => {
  expect(
    parsePostingMetadata(
      "<p>근무지 : <span>서울 성동구</span></p><p>근무 방식 : 원격 근무</p>",
    ),
  ).toEqual({ location: "서울 성동구", workplace: "원격 근무" });
  expect(
    parsePostingMetadata(
      '<style>.x{content:"근무지 : 서울"}</style><img alt="회사 이미지">',
    ),
  ).toEqual({ location: null, workplace: null });
  expect(
    parsePostingMetadata(
      "<p>원격 개발 경력 우대</p><p>근무 방식 : 재택 불가</p>",
    ).workplace,
  ).toBeNull();
  expect(
    parsePostingMetadata("<p>근무 방식 : 하이브리드 근무</p>").workplace,
  ).toBe("하이브리드 근무");
  expect(
    parsePostingMetadata("<p>근무 방식 : 하이브리드 근무 불가</p>").workplace,
  ).toBeNull();
  expect(parsePostingMetadata("<p>근무 방식 : 사무실 근무</p>").workplace).toBe(
    "사무실 근무",
  );
});
