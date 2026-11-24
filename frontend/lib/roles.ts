export const ROLE_IDS = ["data", "backend"] as const;
export type SupportedRole = (typeof ROLE_IDS)[number];
export const roleOptions = [
  { id: "data", label: "데이터" },
  { id: "backend", label: "백엔드" },
] as const;
export function isSupportedRole(value: unknown): value is SupportedRole {
  return value === "data" || value === "backend";
}
// Retired preferences fall back to the first supported choice; evidence stays intact.
export function normalizeRole(value: unknown): SupportedRole {
  return isSupportedRole(value) ? value : "data";
}
export function classifyJobRole(title: string): SupportedRole | null {
  if (
    /\bdata\s+(?:engineer|analyst|scientist|platform)|데이터\s*(?:엔지니어|분석|사이언|플랫폼|개발)/i.test(
      title,
    )
  )
    return "data";
  if (
    /back[ -]?end|백엔드|서버\s*(?:개발|엔지니어)|server[ -]?side/i.test(title)
  )
    return "backend";
  return null;
}
