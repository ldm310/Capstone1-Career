export interface PathItem {
  skill: string;
  title: string;
  optional?: boolean;
}
export interface LearningPath {
  role: string;
  stages: { title: string; description: string; items: PathItem[] }[];
  parallel: PathItem;
}
export const learningPaths: Record<string, LearningPath> = {
  backend: {
    role: "백엔드",
    stages: [
      {
        title: "기초 다지기",
        description: "요청과 응답, 데이터 처리의 기본기를 익혀요.",
        items: [
          { skill: "REST API", title: "HTTP 요청과 응답 다루기" },
          { skill: "SQL", title: "데이터 조회하고 수정하기" },
        ],
      },
      {
        title: "프로젝트 만들기",
        description:
          "서버와 데이터베이스를 연결해요. 구현 언어·프레임워크는 선택할 수 있어요.",
        items: [
          { skill: "PostgreSQL", title: "데이터 저장과 트랜잭션 적용하기" },
          { skill: "REST API", title: "입력 검증과 오류 처리 구현하기" },
        ],
      },
      {
        title: "기능 확장하기",
        description:
          "목표 공고와 프로젝트에 맞는 구현 도구를 선택해요. 모두 배울 필요는 없어요.",
        items: [
          {
            skill: "Spring Boot",
            title: "Java 기반 서버 확장하기",
            optional: true,
          },
          {
            skill: "Node.js",
            title: "JavaScript 기반 서버 확장하기",
            optional: true,
          },
        ],
      },
    ],
    parallel: { skill: "Docker", title: "실행 환경 정리하기" },
  },
  data: {
    role: "데이터",
    stages: [
      {
        title: "기초 다지기",
        description: "필요한 데이터를 읽고 다뤄요.",
        items: [
          { skill: "SQL", title: "데이터 조회하고 집계하기" },
          { skill: "Python", title: "데이터 처리 자동화하기" },
        ],
      },
      {
        title: "프로젝트 만들기",
        description: "저장부터 처리까지 연결해요.",
        items: [
          { skill: "PostgreSQL", title: "데이터 저장 구조 만들기" },
          { skill: "Airflow", title: "데이터 작업 연결하기" },
        ],
      },
      {
        title: "기능 확장하기",
        description: "더 큰 데이터를 처리해 봐요.",
        items: [
          { skill: "Spark", title: "대용량 데이터 처리하기", optional: true },
        ],
      },
    ],
    parallel: { skill: "Docker", title: "실행 환경 정리하기" },
  },
};
