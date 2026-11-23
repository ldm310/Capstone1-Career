import "server-only";
import { profilePool } from "./posting-levels";

export const profileNamespace = () =>
  process.env.CAREER_PROFILE_NAMESPACE || "local-review";
export async function memberRole(subject: string) {
  const connection = profilePool();
  if (!connection) return "MEMBER";
  const result = await connection.query(
    "SELECT app_role FROM public.career_lv_member WHERE namespace=$1 AND subject_id=$2",
    [profileNamespace(), subject],
  );
  return result.rows[0]?.app_role === "ADMIN" ? "ADMIN" : "MEMBER";
}
export function noticeDatabase() {
  const connection = profilePool();
  if (!connection) throw new Error("NOTICE_DATABASE_UNAVAILABLE");
  return connection;
}
export const noticeColumns = `id,title,content,author_name AS "authorName",pinned,created_at AS "createdAt",updated_at AS "updatedAt"`;
