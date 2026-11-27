import { naverConfig } from "@/lib/server/naver";
export function GET() {
  let configured = false;
  try {
    configured = !!naverConfig();
  } catch {}
  return Response.json(
    { configured },
    { headers: { "Cache-Control": "no-store" } },
  );
}
