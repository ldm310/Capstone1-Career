import type { Workspace } from "@/types/workspace";
export function currentFindings(state: Workspace) {
  const sources = new Set<string>();
  return state.runs
    .filter((r) => {
      if (sources.has(r.title)) return false;
      sources.add(r.title);
      return true;
    })
    .flatMap((r) => r.findings);
}
export const targetSkills: Record<string, string[]> = {
  data: ["SQL", "Python", "PostgreSQL", "Airflow", "Spark", "Docker"],
  backend: [
    "REST API",
    "SQL",
    "PostgreSQL",
    "Java",
    "Spring Boot",
    "Node.js",
    "Docker",
    "Git",
  ],
};
export function day(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
