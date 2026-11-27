import { jobKeywords } from "@/lib/server/job-keywords";

export async function GET(request: Request) {
  const { status, body } = await jobKeywords(
    new URL(request.url).searchParams.get("jobId") ?? "",
  );
  return Response.json(body, { status });
}
