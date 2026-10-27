import { leverPosting } from "@/lib/server/analyze";
export const runtime = "nodejs";
export async function GET(request: Request) {
  const url = new URL(request.url).searchParams.get("url") || "";
  try {
    return Response.json(
      { posting: await leverPosting(url) },
      { headers: { "Cache-Control": "public, max-age=600" } },
    );
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : "공고를 불러오지 못했어요." },
      { status: 502 },
    );
  }
}
