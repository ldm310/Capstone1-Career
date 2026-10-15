import { z } from "zod";
const text = z.string().max(2000),
  id = z.string().max(160);
const url = z.union([
  z.literal(""),
  z.url().refine((s) => s.startsWith("https://") || s.startsWith("/api/")),
]);
export const mutation = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("preferences"),
    role: z.enum(["data", "backend"]),
    region: z.string().max(100),
    experience: z.string().max(100),
    hours: z.number().min(1).max(60),
    targetDate: z.string().max(10),
  }),
  z.object({
    action: z.literal("tasks"),
    tasks: z
      .array(
        z.object({
          id,
          title: text,
          date: z.string().max(10),
          done: z.boolean(),
        }),
      )
      .max(200),
  }),
  z.object({
    action: z.literal("events"),
    events: z
      .array(
        z.object({
          id,
          title: text,
          date: z.iso.datetime({ local: true }),
          type: z.enum(["공고 마감", "코딩테스트", "면접", "기타"]),
        }),
      )
      .max(200),
  }),
  z.object({
    action: z.literal("applications"),
    applications: z
      .array(
        z.object({
          id,
          skills: z.array(text).max(100).optional(),
          company: text,
          title: text,
          url,
          stage: z.enum([
            "지원 준비",
            "지원 완료",
            "서류",
            "코딩테스트",
            "면접",
            "최종",
          ]),
          date: z.string().max(10),
          resumeId: id,
          snapshot: z.array(text).max(100),
          notes: z.string().max(10000),
        }),
      )
      .max(200),
  }),
  z.object({
    action: z.literal("answers"),
    answers: z.record(z.string().max(300), z.string().max(10000)),
  }),
  z.object({
    action: z.literal("savedJobs"),
    savedJobs: z
      .array(
        z.object({
          id,
          skills: z.array(text).max(100).optional(),
          company: text,
          title: text,
          category: z.enum(["data", "backend"]),
          location: text,
          employment: text,
          workplace: text.nullable(),
          postedAt: text.nullable(),
          url: z.url().startsWith("https://jobs.lever.co/"),
        }),
      )
      .max(200),
  }),
]);
