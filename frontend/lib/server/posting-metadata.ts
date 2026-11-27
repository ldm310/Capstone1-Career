import type { Pool, PoolClient } from "pg";
type Metadata = {
  id: string;
  location: string | null;
  workplace: string | null;
};
type Database = Pick<Pool | PoolClient, "query">;
const caches = new WeakMap<
  object,
  { expires: number; value: Metadata[]; pending?: Promise<Metadata[]> }
>();
export function parsePostingMetadata(html: string): Omit<Metadata, "id"> {
  const text = html
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "")
    .replace(/<br\b[^>]*>|<\/(?:p|div|li|tr|td|h[1-6])\s*>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\r/g, "");
  const location =
    text
      .match(
        /(?:근무\s*(?:지역|장소|위치|지)|근무\s*주소)[ \t]*[:：][ \t]*([^\n]{2,160})/,
      )?.[1]
      ?.trim() || null;
  let workplace: string | null = null;
  const explicit =
    text.match(
      /근무[ \t]*(?:방식|형태|환경)[ \t]*[:：][ \t]*([^\n]{1,100})/,
    )?.[1] || "";
  if (
    (!/(불가|없음|미제공)/.test(explicit) &&
      /하이브리드|주\s*[1-4]\s*회\s*(재택|원격)/.test(explicit)) ||
    /(?:하이브리드\s*근무|주\s*[1-4]\s*회\s*(?:재택|원격)\s*근무)(?!\s*(?:불가|없음|미제공))/.test(
      text,
    )
  )
    workplace = "하이브리드 근무";
  else if (
    (/^(?:원격|재택)/.test(explicit) && !/(불가|없음|미제공)/.test(explicit)) ||
    /(?:전면\s*재택|100%\s*(?:원격|재택))\s*근무(?!\s*(?:불가|없음|미제공))/.test(
      text,
    )
  )
    workplace = "원격 근무";
  else if (/^(?:사무실|상주|출근)/.test(explicit)) workplace = "사무실 근무";
  return { location, workplace };
}
export async function postingMetadata(db: Database): Promise<Metadata[]> {
  let cache = caches.get(db);
  if (cache?.pending) return cache.pending;
  if (cache && cache.expires > Date.now()) return cache.value;
  cache ??= { expires: 0, value: [] };
  caches.set(db, cache);
  const entry = cache;
  entry.pending = (async () => {
    const { rows } = await db.query(
      "SELECT id::text,body_html FROM public.posting WHERE body_html IS NOT NULL AND body_html<>''",
    );
    const value = rows.map((row: { id: string; body_html: string }) => ({
      id: row.id,
      ...parsePostingMetadata(row.body_html),
    }));
    entry.value = value;
    entry.expires = Date.now() + 60000;
    return value;
  })().finally(() => {
    entry.pending = undefined;
  });
  return entry.pending;
}
