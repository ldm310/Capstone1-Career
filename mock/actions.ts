import type { RecommendedAction } from "@/types/career";
export const actions: RecommendedAction[] = [
  {
    id: "backend-api",
    role: "backend",
    title: "기존 서비스에 API와 입력 검증 구현하기",
    description:
      "요청·응답 규격과 오류 처리를 정리하고 실행 결과를 남겨보세요.",
    type: "implementation",
    skillIds: ["api"],
    duration: "2~3일",
    steps: [
      "API 요청·응답 정의하기",
      "입력 검증과 오류 응답 구현하기",
      "정상·실패 요청 테스트 기록하기",
    ],
  },
  {
    id: "backend-db",
    role: "backend",
    title: "데이터 저장과 트랜잭션 적용하기",
    description: "서비스 데이터 구조를 설계하고 일관성을 확인하세요.",
    type: "implementation",
    skillIds: ["sql", "postgresql"],
    duration: "2~3일",
    steps: [
      "테이블과 제약조건 설계하기",
      "트랜잭션 적용하기",
      "롤백 테스트 결과 기록하기",
    ],
  },
  {
    id: "dockerize",
    role: "backend",
    title: "서버를 Docker로 실행하기",
    description: "프로젝트의 실행 환경과 설정을 문서화하세요.",
    type: "implementation",
    skillIds: ["docker"],
    duration: "1일",
    steps: [
      "Dockerfile 작성하기",
      "컨테이너에서 서버 실행하기",
      "빌드와 실행 명령어 기록하기",
    ],
  },
  {
    id: "data-pipeline",
    role: "data",
    title: "정기 실행 데이터 파이프라인 만들기",
    description:
      "Airflow와 Spark로 작은 ETL 파이프라인을 구현하고 실행 결과를 남겨보세요.",
    type: "implementation",
    skillIds: ["airflow", "spark", "aws"],
    duration: "2~3일",
    steps: [
      "Airflow DAG 만들기",
      "Spark로 데이터 변환하기",
      "AWS 배포 과정 기록하기",
    ],
  },
  {
    id: "data-study",
    role: "data",
    title: "데이터 플랫폼 기본 개념 정리하기",
    description: "배치 처리와 데이터 오케스트레이션 개념을 정리하세요.",
    type: "learning",
    skillIds: ["airflow"],
    duration: "45분",
    steps: ["DAG 개념 살펴보기", "재시도 전략 알아보기", "학습 노트 작성하기"],
  },
];
