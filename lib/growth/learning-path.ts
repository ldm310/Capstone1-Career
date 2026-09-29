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
  ax: {
    role: "AX / LLM 엔지니어",
    stages: [
      {
        title: "기초 다지기",
        description: "서비스를 만들 기본기를 익혀요.",
        items: [{ skill: "Python", title: "데이터 다루기" }],
      },
      {
        title: "프로젝트 만들기",
        description: "내 문서로 답하는 기능을 만들어요.",
        items: [
          { skill: "RAG", title: "문서 검색으로 답변 만들기" },
          { skill: "Vector DB", title: "비슷한 문서 찾아보기" },
        ],
      },
      {
        title: "기능 확장하기",
        description: "여러 작업과 외부 도구를 연결해요.",
        items: [
          { skill: "LangGraph", title: "작업 흐름 연결하기" },
          { skill: "MCP", title: "외부 도구 연결하기", optional: true },
        ],
      },
    ],
    parallel: { skill: "Docker", title: "실행 환경 정리하기" },
  },
  ml: {
    role: "AI / ML 엔지니어",
    stages: [
      {
        title: "기초 다지기",
        description: "데이터 처리의 기본기를 익혀요.",
        items: [{ skill: "Python", title: "데이터 다루기" }],
      },
      {
        title: "프로젝트 만들기",
        description: "학습한 모델을 실행하고 평가해요.",
        items: [{ skill: "PyTorch", title: "모델 학습과 평가하기" }],
      },
      {
        title: "기능 확장하기",
        description: "필요할 때 서비스 운영으로 넓혀요.",
        items: [
          {
            skill: "Kubernetes",
            title: "배포와 운영 살펴보기",
            optional: true,
          },
        ],
      },
    ],
    parallel: { skill: "Docker", title: "실행 환경 정리하기" },
  },
  data: {
    role: "데이터 엔지니어",
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
