import { test, expect } from "@playwright/test";
import {
  toPublicJob,
  type BackendPostingDetail,
} from "@/lib/server/backend-jobs";

// 백엔드 GET /api/postings/{id} 응답 형식(PostingDetailResponse)의 예시.
const detail: BackendPostingDetail = {
  postingId: 12,
  companyName: "예시회사",
  title: "백엔드 개발자 (신입/경력)",
  site: "saramin",
  sitePostingNo: "51234567",
  siteJobCategory: "백엔드/서버개발",
  careerCondition: "신입·경력",
  minYears: 0,
  employmentType: "정규직",
  kind: "글",
  status: "진행",
  deadline: "2026-11-30",
  collectedAt: "2026-10-28T09:00:00+09:00",
  lastCheckedAt: "2026-10-28T09:00:00+09:00",
  analysis: {
    recruitUnits: [
      {
        name: "서버 개발",
        career: "신입·경력",
        items: [
          {
            category: "우대",
            seq: 1,
            text: "Docker 기반 배포 경험",
            requirements: [
              {
                capabilityName: "컨테이너",
                otherName: null,
                techs: [{ techName: "Docker", writtenName: "docker" }],
              },
            ],
          },
          {
            category: "필수",
            seq: 1,
            text: "Java, Spring Boot 개발 경험",
            requirements: [
              {
                capabilityName: "백엔드 프레임워크",
                otherName: null,
                techs: [
                  { techName: "Java", writtenName: "Java" },
                  { techName: null, writtenName: "Spring Boot" },
                ],
              },
            ],
          },
          {
            category: "업무",
            seq: 1,
            text: "주문 API 개발",
            requirements: [],
          },
        ],
      },
    ],
  },
};

test("backend postings become public jobs with sections and skills", () => {
  const job = toPublicJob(detail)!;
  expect(job).toMatchObject({
    id: "be:12",
    company: "예시회사",
    category: "backend",
    employment: "정규직",
    // 백엔드에는 근무지가 없으므로 지어내지 않는다.
    location: "근무지 원문 확인",
    closesAt: "2026-11-30T23:59:59+09:00",
    url: "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=51234567",
    skills: ["Docker", "Java", "Spring Boot"],
  });
  expect(job.experience).toEqual(
    expect.arrayContaining(["entry", "experienced"]),
  );
  expect(job.posting).toEqual([
    { title: "주요 업무", items: ["주문 API 개발"] },
    { title: "자격요건", items: ["Java, Spring Boot 개발 경험"] },
    { title: "우대사항", items: ["Docker 기반 배포 경험"] },
  ]);
});

test("unanalyzed or unsupported backend postings are handled", () => {
  // 추출 전 공고는 본문과 기술이 비어 있다.
  expect(toPublicJob({ ...detail, analysis: null })).toMatchObject({
    skills: [],
    posting: [],
  });
  // 프론트가 다루지 않는 직무(데이터, 백엔드 외)는 뺀다.
  expect(
    toPublicJob({
      ...detail,
      title: "iOS 앱 개발자",
      siteJobCategory: "모바일",
    }),
  ).toBeNull();
});
