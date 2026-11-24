import "server-only";

// A local alias for an existing administrator; it never creates or grants a role.
export function localAdminEmail(request: Request, identifier: string) {
  const hostname = new URL(request.url).hostname;
  const local =
    process.env.NODE_ENV !== "production" &&
    ["127.0.0.1", "localhost"].includes(hostname) &&
    process.env.CAREER_PROFILE_NAMESPACE === "local-review";
  if (!local || identifier !== "admin") return null;
  return process.env.CAREER_LOCAL_ADMIN_EMAIL?.trim().toLowerCase() || null;
}
