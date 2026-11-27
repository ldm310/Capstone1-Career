import { db } from "./store";
import { getPublicJobs } from "@/lib/public-jobs";
import type { PublicJob } from "@/types/public-job";
interface Feed {
  jobs: PublicJob[];
  checkedAt: string;
  unavailableSources: string[];
  stale?: boolean;
}
export function cachedJobFeed(): Feed | null {
  const connection = db();
  connection.exec(
    "CREATE TABLE IF NOT EXISTS job_feed(id INTEGER PRIMARY KEY,data TEXT NOT NULL)",
  );
  const row = connection
    .prepare("SELECT data FROM job_feed WHERE id=1")
    .get() as { data: string } | undefined;
  return row ? JSON.parse(row.data) : null;
}
let pending: Promise<Feed> | null = null;
export function collectedJobs(): Promise<Feed> {
  pending ??= refreshCollectedJobs().finally(() => {
    pending = null;
  });
  return pending;
}
async function refreshCollectedJobs(): Promise<Feed> {
  const d = db();
  d.exec(
    "CREATE TABLE IF NOT EXISTS job_feed(id INTEGER PRIMARY KEY,data TEXT NOT NULL)",
  );
  const cached = d.prepare("SELECT data FROM job_feed WHERE id=1").get() as
    { data: string } | undefined;
  const previous: Feed | null = cached ? JSON.parse(cached.data) : null;
  if (previous && Date.now() - Date.parse(previous.checkedAt) < 300000)
    return previous;
  try {
    const feed = await getPublicJobs();
    d.prepare(
      "INSERT INTO job_feed VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
    ).run(JSON.stringify(feed));
    return feed;
  } catch (e) {
    if (previous)
      return {
        ...previous,
        stale: true,
        unavailableSources: [
          "현재 수집에 실패해 마지막으로 확인한 공고를 보여드려요. 마감 여부는 원문에서 확인하세요.",
        ],
      };
    throw e;
  }
}
