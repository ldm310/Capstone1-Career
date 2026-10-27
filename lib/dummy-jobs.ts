import type { PostingSection, PublicJob } from "@/types/public-job";

// 공고 본문 섹션을 분석기가 읽는 텍스트로 바꾼다. 섹션 제목이 줄 머리에 와야 필수, 우대가 구분된다.
export function postingText(sections: PostingSection[]) {
  return sections.flatMap((s) => [s.title, ...s.items]).join("\n");
}

// 더미 공고: 실제 수집 공고가 적을 때 목록, 상세, 역량 비교 화면을 확인하기 위한 가상 데이터다.
// 원문 페이지가 없으므로 posting을 공고 본문으로 사용한다.
export const dummyJobs: (PublicJob & { posting: PostingSection[] })[] = [
  {
    id: "dummy:backend-platform",
    dummy: true,
    company: "클라우드웨이브",
    title: "백엔드 플랫폼 엔지니어",
    category: "backend",
    location: "서울 강남구",
    employment: "정규직",
    experience: ["entry", "experienced"],
    workplace: "하이브리드 근무",
    postedAt: "2026-10-20T00:00:00+09:00",
    closesAt: "2026-11-30T18:00:00+09:00",
    url: "https://jobs.lever.co/career-example/backend-platform",
    skills: ["Java", "Spring Boot", "PostgreSQL", "Docker", "REST API"],
    posting: [
      {
        title: "회사 소개",
        items: [
          "클라우드웨이브는 중소 쇼핑몰을 위한 주문, 결제 플랫폼을 만듭니다.",
          "하루 30만 건의 주문을 안정적으로 처리하는 것이 목표예요.",
        ],
      },
      {
        title: "주요 업무",
        items: [
          "주문, 결제 서비스의 REST API 설계와 운영",
          "트래픽 증가에 맞춘 데이터베이스 구조 개선",
          "장애 대응과 모니터링 체계 개선",
        ],
      },
      {
        title: "자격요건",
        items: [
          "Java와 Spring Boot로 서비스를 개발한 경험",
          "PostgreSQL 등 관계형 데이터베이스와 SQL 활용 경험",
          "Git으로 협업한 경험",
        ],
      },
      {
        title: "우대사항",
        items: [
          "Docker 기반 배포 경험",
          "Kubernetes 운영 경험",
          "결제 도메인 경험",
        ],
      },
      {
        title: "근무 조건",
        items: ["주 2회 재택, 유연 출퇴근 (10시~16시 코어타임)", "수습 3개월"],
      },
      {
        title: "채용 절차",
        items: ["서류 전형", "과제 전형", "기술 면접", "최종 면접"],
      },
    ],
  },
  {
    id: "dummy:data-engineer",
    dummy: true,
    company: "데이터브릿지",
    title: "데이터 엔지니어",
    category: "data",
    location: "경기 성남시",
    employment: "정규직",
    experience: ["experienced"],
    workplace: "사무실 근무",
    postedAt: "2026-10-18T00:00:00+09:00",
    closesAt: "2026-11-15T18:00:00+09:00",
    url: "https://jobs.lever.co/career-example/data-engineer",
    skills: ["Python", "SQL", "Airflow", "Spark"],
    posting: [
      {
        title: "회사 소개",
        items: ["데이터브릿지는 광고 성과 분석 솔루션을 만드는 B2B 회사예요."],
      },
      {
        title: "주요 업무",
        items: [
          "서비스 로그를 모아 분석용 데이터 파이프라인 구축",
          "배치 작업 일정 관리와 장애 복구",
          "분석팀이 쓰는 데이터 마트 설계",
        ],
      },
      {
        title: "자격요건",
        items: [
          "Python과 SQL로 데이터를 처리한 경험",
          "Airflow로 배치 작업을 운영한 경험",
          "실무 경력 2년 이상",
        ],
      },
      {
        title: "우대사항",
        items: [
          "Spark로 대용량 데이터를 처리한 경험",
          "Docker 사용 경험",
          "클라우드 데이터 웨어하우스 경험",
        ],
      },
      {
        title: "근무 조건",
        items: ["판교 사무실 근무", "연 1회 교육비 지원"],
      },
      {
        title: "채용 절차",
        items: ["서류 전형", "실무 면접", "최종 면접"],
      },
    ],
  },
  {
    id: "dummy:junior-api",
    dummy: true,
    company: "핀테크랩",
    title: "주니어 API 서버 개발자",
    category: "backend",
    location: "서울 영등포구",
    employment: "정규직",
    experience: ["entry"],
    workplace: "원격 근무",
    postedAt: "2026-10-15T00:00:00+09:00",
    closesAt: "2026-11-20T18:00:00+09:00",
    url: "https://jobs.lever.co/career-example/junior-api",
    skills: ["Node.js", "REST API", "SQL", "Git"],
    posting: [
      {
        title: "회사 소개",
        items: ["핀테크랩은 소상공인을 위한 간편 정산 앱을 만들어요."],
      },
      {
        title: "주요 업무",
        items: [
          "정산, 알림 기능의 REST API 개발",
          "외부 결제사 API 연동",
          "테스트 코드 작성과 코드 리뷰",
        ],
      },
      {
        title: "자격요건",
        items: [
          "Node.js로 서버를 만들어 본 경험",
          "SQL로 데이터를 조회하고 수정한 경험",
          "Git으로 협업한 경험",
        ],
      },
      {
        title: "우대사항",
        items: ["Docker 사용 경험", "금융 서비스 관심"],
      },
      {
        title: "근무 조건",
        items: ["전면 원격 근무, 월 1회 오프라인 모임", "장비 지원"],
      },
      {
        title: "채용 절차",
        items: ["서류 전형", "코딩 테스트", "면접"],
      },
    ],
  },
];
