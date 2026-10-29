import type { Finding } from "@/types/workspace";
export const id = () => crypto.randomUUID();
export const evidenceLabel = (f: Finding) =>
  f.type === "implementation"
    ? "코드에서 발견"
    : f.type === "learning"
      ? "학습 자료에서 발견"
      : "경력 문서에서 발견";
