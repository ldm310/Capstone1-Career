import { kakaoConfig } from "@/lib/server/kakao";
export function GET() {
  let configured = false;
  try {
    configured = !!kakaoConfig();
  } catch {}
  return Response.json(
    { configured },
    { headers: { "Cache-Control": "no-store" } },
  );
}
