import { originCheck } from "@/lib/server/store";
import { cancelKakaoRegistration } from "@/lib/server/kakao-registration";
export const runtime = "nodejs";
export async function DELETE(request: Request) {
  try {
    originCheck(request);
  } catch {
    return Response.json(
      { error: "요청 출처를 확인해 주세요." },
      { status: 403 },
    );
  }
  await cancelKakaoRegistration();
  return Response.json(
    { ok: true },
    { headers: { "Cache-Control": "no-store" } },
  );
}
