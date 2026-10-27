import { db, passwordHash, saveWorkspace } from "./store";
import {
  emptyWorkspace,
  type Finding,
  type Workspace,
} from "@/types/workspace";
import type { GrowthState } from "@/types/growth";

// 데모 로그인 계정: 이미 자료를 올리고 분석까지 마친 사용자를 흉내 내는 더미 데이터다.
export const demoAccount = {
  email: "demo@career.dev",
  password: "career-demo-2026",
  name: "김커리어",
};
const userId = "demo-user";
const resumeId = "demo-doc-resume";
const notesId = "demo-doc-notes";
const repo = "https://github.com/career-demo/order-service";
const at = "2026-10-20T09:00:00.000Z";

const resumeText = [
  "김커리어 이력서",
  "학력: 컴퓨터공학과 졸업 (2026.02)",
  "경력: 스타트업 백엔드 인턴 6개월, 주문 API 개발과 SQL 쿼리 개선",
  "프로젝트: 주문 관리 서비스 - Java, Spring Boot, PostgreSQL로 REST API 구현",
  "프로젝트: 팀 프로젝트 - Docker로 개발 환경 통일, Git 브랜치 전략 운영",
  "자격증: 정보처리기사, SQLD",
].join("\n");
const notesText = [
  "# 학습 노트",
  "## Kubernetes",
  "Pod, Deployment, Service 개념을 정리하고 minikube로 실습했다.",
  "## Redis",
  "캐시 전략(Cache Aside)을 공부하고 조회 API에 적용해 볼 계획이다.",
].join("\n");

const finding = (
  id: string,
  skill: string,
  type: Finding["type"],
  title: string,
  quote: string,
  url: string,
): Finding => ({ id, skill, type, title, quote, url, detectedAt: at });

const githubFindings: Finding[] = [
  finding(
    "demo-f-java",
    "Java",
    "implementation",
    "OrderService.java",
    "public Order create(OrderRequest request) {\n  validate(request);\n  return repository.save(Order.from(request));\n}",
    `${repo}/blob/main/src/main/java/demo/order/OrderService.java#L18`,
  ),
  finding(
    "demo-f-spring",
    "Spring Boot",
    "implementation",
    "OrderController.java",
    '@RestController\n@RequestMapping("/api/orders")\npublic class OrderController {',
    `${repo}/blob/main/src/main/java/demo/order/OrderController.java#L9`,
  ),
  finding(
    "demo-f-rest",
    "REST API",
    "implementation",
    "OrderController.java",
    "@PostMapping\npublic ResponseEntity<OrderResponse> create(@Valid @RequestBody OrderRequest request)",
    `${repo}/blob/main/src/main/java/demo/order/OrderController.java#L21`,
  ),
  finding(
    "demo-f-postgres",
    "PostgreSQL",
    "implementation",
    "application.yml",
    "datasource:\n  url: jdbc:postgresql://db:5432/orders",
    `${repo}/blob/main/src/main/resources/application.yml#L4`,
  ),
  finding(
    "demo-f-sql",
    "SQL",
    "implementation",
    "V2__order_index.sql",
    "CREATE INDEX idx_orders_user_created ON orders(user_id, created_at DESC);",
    `${repo}/blob/main/src/main/resources/db/migration/V2__order_index.sql#L1`,
  ),
  finding(
    "demo-f-docker",
    "Docker",
    "implementation",
    "docker-compose.yml",
    "services:\n  api:\n    build: .\n  db:\n    image: postgres:16",
    `${repo}/blob/main/docker-compose.yml#L1`,
  ),
];
const resumeFindings: Finding[] = [
  finding(
    "demo-f-resume-sql",
    "SQL",
    "career",
    "이력서.md",
    "경력: 스타트업 백엔드 인턴 6개월, 주문 API 개발과 SQL 쿼리 개선",
    `/documents/${resumeId}#L3`,
  ),
  finding(
    "demo-f-resume-git",
    "Git",
    "career",
    "이력서.md",
    "프로젝트: 팀 프로젝트 - Docker로 개발 환경 통일, Git 브랜치 전략 운영",
    `/documents/${resumeId}#L5`,
  ),
];
const notesFindings: Finding[] = [
  finding(
    "demo-f-notes-k8s",
    "Kubernetes",
    "learning",
    "학습 노트.md",
    "Pod, Deployment, Service 개념을 정리하고 minikube로 실습했다.",
    `/documents/${notesId}#L3`,
  ),
];

function demoWorkspace(): Workspace {
  return {
    ...structuredClone(emptyWorkspace),
    role: "backend",
    region: "서울",
    experience: "신입",
    hours: 8,
    targetDate: "2026-12-31",
    runs: [
      {
        id: "demo-run-github",
        title: "career-demo/order-service",
        at,
        findings: githubFindings,
      },
      {
        id: "demo-run-resume",
        title: "이력서.md",
        at,
        findings: resumeFindings,
      },
      {
        id: "demo-run-notes",
        title: "학습 노트.md",
        at,
        findings: notesFindings,
      },
    ],
    documents: [
      { id: resumeId, name: "이력서.md", at },
      { id: notesId, name: "학습 노트.md", at },
    ],
    tasks: [
      {
        id: "demo-plan-1",
        title: "Kubernetes 공식 문서 읽고 메모하기",
        date: "2026-10-28",
        done: true,
      },
      {
        id: "demo-plan-2",
        title: "Kubernetes를 프로젝트에 구현하기",
        date: "2026-10-30",
        done: false,
      },
      {
        id: "demo-plan-3",
        title: "Kubernetes 코드, 설명 근거 정리하기",
        date: "2026-11-01",
        done: false,
      },
    ],
    answers: {
      "Spring Boot":
        "주문 서비스에서 Spring Boot로 REST API를 만들었습니다. 입력 검증은 @Valid로 처리했고, 예외는 공통 핸들러로 모아 응답 형식을 통일했습니다.",
    },
  };
}

function demoGrowth(): GrowthState {
  const review = (
    skill: string,
    level: 1 | 2 | 3 | null,
    status: GrowthState["reviews"][number]["status"],
    evidenceIds: string[],
    reason: string,
  ) => ({ skill, original: skill, level, status, reason, evidenceIds });
  return {
    reviews: [
      review(
        "Java",
        2,
        "confirmed",
        ["demo-f-java"],
        "서비스 계층 코드에서 확인했어요.",
      ),
      review(
        "Spring Boot",
        2,
        "confirmed",
        ["demo-f-spring"],
        "컨트롤러와 검증 코드에서 확인했어요.",
      ),
      review(
        "REST API",
        2,
        "confirmed",
        ["demo-f-rest"],
        "입력 검증과 응답 처리를 확인했어요.",
      ),
      review(
        "PostgreSQL",
        2,
        "confirmed",
        ["demo-f-postgres"],
        "서비스 DB 연결 설정을 확인했어요.",
      ),
      review(
        "SQL",
        3,
        "confirmed",
        ["demo-f-sql", "demo-f-resume-sql"],
        "인덱스로 쿼리를 개선한 기록이 있어요.",
      ),
      review(
        "Docker",
        1,
        "pending",
        ["demo-f-docker"],
        "compose 실행 설정을 찾았어요. 수준은 확인 전이에요.",
      ),
      review(
        "Git",
        null,
        "pending",
        ["demo-f-resume-git"],
        "이력서에서 찾은 기술이에요.",
      ),
      review(
        "Kubernetes",
        null,
        "pending",
        ["demo-f-notes-k8s"],
        "학습 노트에서 찾은 기술이에요.",
      ),
    ],
    tasks: [
      {
        id: "demo-task-docker",
        skill: "Docker",
        level: 2,
        baseline: 1,
        baselineEvidence: ["demo-f-docker"],
        startedAt: "2026-10-22T09:00:00.000Z",
        date: "2026-11-05",
        status: "active",
        submissions: [],
      },
      {
        id: "demo-task-postgres",
        skill: "PostgreSQL",
        level: 3,
        baseline: 2,
        baselineEvidence: ["demo-f-postgres"],
        startedAt: "2026-10-15T09:00:00.000Z",
        date: "2026-10-25",
        status: "needs_evidence",
        submissions: [
          {
            at: "2026-10-24T09:00:00.000Z",
            evidence: `${repo}/commit/a1b2c3d`,
            explanation:
              "주문 조회 쿼리에 복합 인덱스를 추가하고 실행 계획을 비교했습니다. 응답 시간이 320ms에서 45ms로 줄었습니다.",
            feedback: "저장했어요. 검토 기능은 준비 중이에요.",
          },
        ],
      },
    ],
  };
}

// 데모 계정이 없으면 계정과 자료를 만든다. 이미 있으면 그대로 둔다.
export function ensureDemoAccount() {
  const d = db();
  if (d.prepare("SELECT id FROM users WHERE email=?").get(demoAccount.email))
    return;
  d.exec(
    "CREATE TABLE IF NOT EXISTS growth(user_id TEXT PRIMARY KEY,data TEXT NOT NULL)",
  );
  d.prepare("INSERT INTO users VALUES(?,?,?,?)").run(
    userId,
    demoAccount.email,
    demoAccount.name,
    passwordHash(demoAccount.password),
  );
  const insertDoc = d.prepare(
    "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?)",
  );
  insertDoc.run(
    resumeId,
    userId,
    "이력서.md",
    "text/markdown",
    Buffer.from(resumeText),
    resumeText,
  );
  insertDoc.run(
    notesId,
    userId,
    "학습 노트.md",
    "text/markdown",
    Buffer.from(notesText),
    notesText,
  );
  saveWorkspace(userId, demoWorkspace());
  d.prepare(
    "INSERT INTO growth VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
  ).run(userId, JSON.stringify(demoGrowth()));
}
