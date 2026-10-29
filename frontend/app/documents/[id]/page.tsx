import Link from "next/link";
import { db, user } from "@/lib/server/store";
import { redirect, notFound } from "next/navigation";
export const dynamic = "force-dynamic";
export default async function Document({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const account = await user();
  if (!account) redirect("/sign-in");
  const { id } = await params;
  const row = db()
    .prepare("SELECT name,text FROM documents WHERE id=? AND user_id=?")
    .get(id, account.id) as { name: string; text: string } | undefined;
  if (!row) notFound();
  return (
    <main className="document-reader">
      <Link href="/my-data">← 내 자료</Link>
      <h1>{row.name}</h1>
      <p>추출한 텍스트라 원문과 다를 수 있어요.</p>
      <a href={`/api/documents/${id}`}>원본 내려받기</a>
      <div>
        {row.text.split("\n").map((line, index) => (
          <p className="document-line" id={`L${index + 1}`} key={index}>
            <a href={`#L${index + 1}`} aria-label={`${index + 1}번째 줄`}>
              {index + 1}
            </a>
            <span>{line || " "}</span>
          </p>
        ))}
      </div>
    </main>
  );
}
