import { z } from "zod";
import { db } from "./store";
import { emptyProfile, type Profile } from "@/types/profile";
import type { PublicJob } from "@/types/public-job";

const text = (max: number) => z.string().trim().max(max).default("");
export const profileSchema = z.object({
  education: text(30),
  school: text(60),
  major: text(60),
  career: text(30),
  location: text(60),
  github: z.union([z.literal(""), z.url().max(200)]).default(""),
  intro: text(200),
});

export function profile(userId: string): Profile {
  const row = db()
    .prepare("SELECT data FROM profiles WHERE user_id=?")
    .get(userId) as { data: string } | undefined;
  if (!row) return { ...emptyProfile };
  const parsed = profileSchema.safeParse(JSON.parse(row.data));
  return parsed.success ? parsed.data : { ...emptyProfile };
}
export function saveProfile(userId: string, data: Profile) {
  db()
    .prepare(
      "INSERT INTO profiles VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
    )
    .run(userId, JSON.stringify(data));
}

// 저장한 공고: 저장 시점의 공고 내용을 같이 보관해 마감되거나 목록에서 빠져도 보여준다.
export const savedJobSchema = z
  .object({
    id: z.string().min(1).max(300),
    company: z.string().max(200),
    title: z.string().max(300),
    category: z.enum(["data", "backend"]),
    location: z.string().max(200),
    employment: z.string().max(100),
    workplace: z.string().max(100).nullable(),
    postedAt: z.string().max(40).nullable(),
    closesAt: z.string().max(40).nullable().optional(),
    url: z.string().max(500),
    dummy: z.boolean().optional(),
    skills: z.array(z.string().max(60)).max(40).optional(),
    experience: z
      .array(z.enum(["entry", "experienced", "intern", "any"]))
      .max(4)
      .optional(),
  })
  .strip();
export type SavedJob = PublicJob & { savedAt: string };
export function savedJobs(userId: string): SavedJob[] {
  const rows = db()
    .prepare(
      "SELECT data,saved_at FROM saved_jobs WHERE user_id=? ORDER BY saved_at DESC",
    )
    .all(userId) as { data: string; saved_at: number }[];
  return rows.map((r) => ({
    ...(JSON.parse(r.data) as PublicJob),
    savedAt: new Date(r.saved_at).toISOString(),
  }));
}
export function saveJob(userId: string, job: PublicJob, at = Date.now()) {
  db()
    .prepare(
      "INSERT INTO saved_jobs VALUES(?,?,?,?) ON CONFLICT(user_id,job_id) DO UPDATE SET data=excluded.data",
    )
    .run(userId, job.id, JSON.stringify(job), at);
}
export function removeSavedJob(userId: string, jobId: string) {
  db()
    .prepare("DELETE FROM saved_jobs WHERE user_id=? AND job_id=?")
    .run(userId, jobId);
}
