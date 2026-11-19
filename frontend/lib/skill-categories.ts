// Same flat taxonomy as GET /api/skill-categories. Keywords here are display
// fixtures, not a replacement for the saved sentence classifier or LV rules.
export const skillCategories = [
  {
    code: "L",
    name: "프로그래밍·CS 기초",
    label: ["프로그래밍", "CS 기초"],
    keywords: ["Java", "Python", "자료구조"],
  },
  {
    code: "B",
    name: "백엔드 개발",
    label: ["백엔드", "개발"],
    keywords: ["Spring Boot", "REST API", "Node.js"],
  },
  {
    code: "D",
    name: "데이터베이스",
    label: ["데이터베이스"],
    keywords: ["SQL", "PostgreSQL", "Redis"],
  },
  {
    code: "E",
    name: "데이터 엔지니어링·분석",
    label: ["데이터", "엔지니어링·분석"],
    keywords: ["Airflow", "Spark", "데이터 분석"],
  },
  {
    code: "O",
    name: "인프라·배포·운영",
    label: ["인프라", "배포·운영"],
    keywords: ["Docker", "AWS", "Kubernetes"],
  },
  {
    code: "Q",
    name: "코드 품질·테스트",
    label: ["코드 품질", "테스트"],
    keywords: ["테스트", "리팩터링", "코드 리뷰"],
  },
  {
    code: "F",
    name: "프론트엔드·앱 개발",
    label: ["프론트엔드", "앱 개발"],
    keywords: ["React", "TypeScript", "Flutter"],
  },
  {
    code: "A",
    name: "AI 기술",
    label: ["AI 기술"],
    keywords: ["RAG", "PyTorch", "LangGraph"],
  },
  {
    code: "S",
    name: "보안·개인정보보호",
    label: ["보안", "개인정보보호"],
    keywords: ["OAuth", "취약점 점검", "개인정보보호"],
  },
  {
    code: "H",
    name: "임베디드·장비 제어·연동",
    label: ["임베디드", "장비 제어·연동"],
    keywords: ["IoT", "ROS", "장비 제어"],
  },
] as const;

export type SkillCategoryCode = (typeof skillCategories)[number]["code"];
export const categoryKeywords = skillCategories.flatMap((category) => [
  ...category.keywords,
]);

export function categoryLevels(levels: Record<string, number>) {
  return Object.fromEntries(
    skillCategories.map((category) => {
      const values = category.keywords
        .map((key) => levels[key])
        .filter((value) => Number.isFinite(value));
      return [
        category.code,
        values.length
          ? Math.round(
              values.reduce((sum, value) => sum + value, 0) / values.length,
            )
          : 0,
      ];
    }),
  ) as Record<SkillCategoryCode, number>;
}
