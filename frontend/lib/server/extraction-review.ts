import "server-only";
import { profilePool } from "./posting-levels";

export function reviewDatabase() {
  const pool = profilePool();
  if (!pool) throw new Error("EXTRACTION_REVIEW_UNAVAILABLE");
  return pool;
}
