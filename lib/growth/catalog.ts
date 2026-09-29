import type { Level } from "@/types/growth";
export const levelNames = {
  1: "기초 사용",
  2: "프로젝트 적용",
  3: "개선·문제 해결",
};
export const rewards = { 1: 10, 2: 20, 3: 30 };
export const criteria: Record<string, [string, string, string]> = {
  Python: [
    "입력·처리·출력이 있는 프로그램과 기본 테스트",
    "모듈화·예외 처리·외부 데이터 연동",
    "성능 또는 구조 문제의 측정과 개선 전후 비교",
  ],
  SQL: [
    "조건·집계·조인 쿼리와 결과 검증",
    "데이터 구조 설계와 트랜잭션 처리",
    "실행 계획에 근거한 쿼리 개선과 전후 비교",
  ],
  PostgreSQL: [
    "테이블·제약조건·CRUD 실행",
    "인덱스·트랜잭션의 서비스 적용",
    "동시성·성능 또는 복구 문제 해결과 검증",
  ],
  Docker: [
    "Dockerfile 작성·이미지 빌드·컨테이너 실행",
    "앱과 DB 연결·설정 분리·데이터 유지·재현 가능한 실행 설명",
    "보안 또는 이미지 최적화와 효과 검증",
  ],
  RAG: [
    "문서 검색을 이용한 답변 생성",
    "문서 분할·검색·출처 표시·평가 연결",
    "검색·답변 오류 분석과 개선 전후 비교",
  ],
  "Vector DB": [
    "데이터 저장과 유사도 검색",
    "메타데이터 필터·데이터 업데이트의 서비스 적용",
    "검색 품질·지연시간 측정과 최적화",
  ],
  LangGraph: [
    "상태·노드·분기 구성",
    "도구 호출·상태 저장·예외 및 재시도 처리",
    "복구·관측·사람의 승인 흐름 검증",
  ],
  MCP: [
    "도구 서버 제공과 클라이언트 호출",
    "실제 데이터 연동·입력 검증·오류 처리",
    "접근 제어·호환성·운영 안정성 검증",
  ],
  PyTorch: [
    "모델 학습과 평가",
    "검증 데이터·재현 실험·모델 저장과 추론",
    "오류 분석·비교 실험·비용과 성능 설명",
  ],
  Airflow: [
    "DAG와 작업 의존성 구성",
    "재시도·중복 실행 대응 파이프라인",
    "실패 복구·백필·처리 성능 검증",
  ],
  Spark: [
    "데이터 읽기·변환·집계",
    "조인·파티션을 고려한 파이프라인",
    "병목·데이터 쏠림 분석과 성능 개선",
  ],
  Kubernetes: [
    "앱 배포와 서비스 연결",
    "설정·상태 검사·자원 제한·업데이트",
    "장애 대응·확장·접근 제어 검증",
  ],
};
export function canonical(name: string) {
  const aliases: Record<string, string> = {
    k8s: "Kubernetes",
    postgres: "PostgreSQL",
    postgresql: "PostgreSQL",
    pytorch: "PyTorch",
  };
  return (
    aliases[name.toLowerCase()] ||
    Object.keys(criteria).find((s) => s.toLowerCase() === name.toLowerCase()) ||
    name
  );
}
export function requirement(skill: string, level: Level) {
  return (
    criteria[skill]?.[level - 1] ||
    "이 기술의 평가 기준은 준비 중이에요. 자료는 먼저 보관할 수 있어요."
  );
}
export function denseRanking<T extends { id: string; points: number }>(
  rows: T[],
) {
  let rank = 0,
    previous = -1;
  return [...rows]
    .sort((a, b) => b.points - a.points || a.id.localeCompare(b.id))
    .map((row) => {
      if (row.points !== previous) rank++;
      previous = row.points;
      return { ...row, rank };
    });
}
