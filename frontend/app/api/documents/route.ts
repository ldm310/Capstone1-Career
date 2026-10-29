import { randomUUID } from "node:crypto";
import {
  db,
  requireUser,
  workspace,
  saveWorkspace,
  originCheck,
  failure,
  rateLimit,
} from "@/lib/server/store";
import { extract } from "@/lib/server/analyze";
export const runtime = "nodejs";
export async function POST(req: Request) {
  try {
    originCheck(req);
    const u = await requireUser();
    rateLimit("docs:" + u.id, 20);
    if (Number(req.headers.get("content-length")) > 11000000)
      throw new Error("파일은 10MB 이하로 선택하세요.");
    const form = await req.formData();
    const file = form.get("file");
    if (!(file instanceof File) || file.size > 10000000)
      throw new Error("10MB 이하의 파일을 선택하세요.");
    const bytes = Buffer.from(await file.arrayBuffer());
    let text = "";
    let mime = "text/plain";
    if (/\.pdf$/i.test(file.name)) {
      const { PDFParse } = await import("pdf-parse");
      const parser = new PDFParse({ data: bytes });
      try {
        text = (await parser.getText()).text;
      } finally {
        await parser.destroy();
      }
      mime = "application/pdf";
    } else if (/\.md$/i.test(file.name)) {
      text = bytes.toString("utf8");
    } else throw new Error("PDF 또는 Markdown(.md) 파일을 선택해 주세요.");
    if (text.trim().length < 10)
      throw new Error(
        "읽을 수 있는 텍스트가 없습니다. 스캔 문서는 OCR 후 업로드하세요.",
      );
    text = text.slice(0, 150000);
    const id = randomUUID(),
      at = new Date().toISOString();
    const state = workspace(u.id);
    if (state.documents.length >= 100)
      throw new Error("문서는 최대 100개까지 저장할 수 있습니다.");
    db()
      .prepare("INSERT INTO documents VALUES(?,?,?,?,?,?)")
      .run(id, u.id, file.name, mime, bytes, text);
    state.documents.unshift({ id, name: file.name, at });
    state.runs = [
      {
        id: randomUUID(),
        at,
        title: file.name,
        findings: extract(
          text,
          file.name,
          `/documents/${id}`,
          form.get("source") === "notion" ? "learning" : "career",
        ),
      },
      ...state.runs,
    ].slice(0, 30);
    saveWorkspace(u.id, state);
    return Response.json({ workspace: state });
  } catch (e) {
    return failure(e);
  }
}
