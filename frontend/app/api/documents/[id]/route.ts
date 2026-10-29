import { db, requireUser } from "@/lib/server/store";
export const runtime = "nodejs";
export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const u = await requireUser();
    const { id } = await params;
    const row = db()
      .prepare("SELECT * FROM documents WHERE id=? AND user_id=?")
      .get(id, u.id) as
      | { name: string; mime: string; bytes: Uint8Array; text: string }
      | undefined;
    if (!row) return new Response("문서가 없습니다.", { status: 404 });
    if (new URL(req.url).searchParams.get("view") === "text")
      return new Response(row.text, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    return new Response(new Uint8Array(row.bytes), {
      headers: {
        "Content-Type": row.mime,
        "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(row.name)}`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("로그인이 필요합니다.", { status: 401 });
  }
}
