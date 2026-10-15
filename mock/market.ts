import type { MarketDataset, RoleId } from "@/types/career";
import { skills } from "./skills";
function dataset(
  ids: string[],
  demands: number[],
  changes: number[],
  total: number,
  relationships: string[][],
): MarketDataset {
  const ranking = ids.map((skillId, i) => ({
    skillId,
    name: skills.find((s) => s.id === skillId)!.name,
    demand: demands[i],
    change: changes[i],
  }));
  return {
    skills: ranking,
    total,
    relationships,
    trend: ["4월", "5월", "6월", "7월", "8월", "9월"].map((month, i) =>
      Object.fromEntries([
        ["month", month],
        ...ranking
          .slice(0, 3)
          .map((s) => [
            s.name,
            Math.max(1, s.demand - (s.change * (5 - i)) / 3),
          ]),
      ]),
    ) as MarketDataset["trend"],
  };
}
export const market: Record<RoleId, MarketDataset> = {
  backend: dataset(
    ["api", "sql", "postgresql", "java", "spring", "nodejs", "docker", "git"],
    [85, 79, 63, 61, 57, 46, 42, 40],
    [2, 1, 3, 1, 2, 3, 4, 1],
    250,
    [
      ["REST API", "SQL", "PostgreSQL"],
      ["Java", "Spring Boot"],
      ["Node.js", "Docker", "Git"],
    ],
  ),
  data: dataset(
    ["sql", "python", "spark", "airflow", "aws", "docker"],
    [86, 73, 56, 49, 43, 35],
    [1, 2, 5, 8, 4, 1],
    312,
    [
      ["Ingestion", "Airflow", "Spark", "SQL"],
      ["Platform", "AWS", "Docker"],
    ],
  ),
};
