import type {
  CareerDataset,
  Evidence,
  PersonalSkill,
  RoleId,
  SkillGap,
} from "@/types/career";
export function personalSkills(evidence: Evidence[]): PersonalSkill[] {
  return [...new Set(evidence.map((e) => e.skillId))].map((skillId) => ({
    skillId,
    evidenceIds: evidence.filter((e) => e.skillId === skillId).map((e) => e.id),
  }));
}
export function evidenceStatus(skillId: string, evidence: Evidence[]) {
  const found = evidence.filter((e) => e.skillId === skillId);
  return found.some((e) => e.type === "implementation")
    ? "implementation"
    : found.some((e) => e.type === "career")
      ? "career"
      : found.some((e) => e.type === "certificate")
        ? "certificate"
        : found.length
          ? "learning"
          : "none";
}
export function getCoverage(
  data: CareerDataset,
  role: RoleId,
  evidence: Evidence[],
) {
  const required = data.roles.find((r) => r.id === role)!.skills;
  const count = required.filter((id) =>
    evidence.some((e) => e.skillId === id),
  ).length;
  return {
    count,
    total: required.length,
    percent: Math.round((count / required.length) * 100),
  };
}
export function getGaps(
  data: CareerDataset,
  role: RoleId,
  evidence: Evidence[],
): SkillGap[] {
  return data.market[role].skills
    .filter((s) =>
      ["none", "learning"].includes(evidenceStatus(s.skillId, evidence)),
    )
    .map((s) => ({
      skillId: s.skillId,
      name: s.name,
      demand: s.demand,
      status:
        evidenceStatus(s.skillId, evidence) === "none"
          ? ("none" as const)
          : ("learning-only" as const),
      trend: s.change,
    }))
    .sort((a, b) => b.demand - a.demand);
}
export function skillName(data: CareerDataset, id: string) {
  return data.skills.find((s) => s.id === id)?.name ?? id;
}

export function getHeroPreview(data: CareerDataset) {
  const implemented = data.evidence
    .filter((e) => e.type === "implementation")
    .slice(0, 2);
  return {
    market: data.market.data.skills.filter((s) =>
      ["sql", "python", "airflow"].includes(s.skillId),
    ),
    evidenceTitle: implemented[0]?.title ?? "Your next project",
    evidenceSkills: implemented.map((e) => skillName(data, e.skillId)),
    opportunity:
      data.market.data.skills.find((s) => s.skillId === "airflow")?.name ??
      "Your next skill",
  };
}
