import type { Pool, PoolClient } from "pg";
import {
  eligiblePostingSql,
  closedPostingSql,
  visibilityNamespaceSql,
} from "./posting-metadata-sql";

type Database = Pick<Pool | PoolClient, "query">;
export type PublicationStatus = "PUBLISHED" | "HIDDEN" | "FILTERED" | "CLOSED";
export type PublicationItem = {
  id: string;
  company: string;
  title: string;
  site: string;
  postingNo: string;
  deadline: string | null;
  hidden: boolean;
  revision: number;
  eligible: boolean;
  state: PublicationStatus;
  sourceUrl: string;
};
const namespace = visibilityNamespaceSql;
export async function listPostingPublication(
  db: Database,
  status: PublicationStatus,
  query: string,
  offset: number,
) {
  const { rows } = await db.query(
    `WITH records AS (
    SELECT p.id::text,c.name AS company,p.title,p.site,p.site_posting_no AS "postingNo",p.deadline,
      coalesce(v.hidden,false) AS hidden,coalesce(v.revision,0) AS revision,
      (${eligiblePostingSql("p")}) AS eligible,
      CASE WHEN v.hidden THEN 'HIDDEN' WHEN ${closedPostingSql("p")} THEN 'CLOSED'
        WHEN ${eligiblePostingSql("p")} THEN 'PUBLISHED' ELSE 'FILTERED' END AS state,
      CASE WHEN p.site IN ('사람인','saramin') AND p.site_posting_no ~ '^[0-9]+$'
        THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx='||p.site_posting_no ELSE '' END AS "sourceUrl"
    FROM public.posting p JOIN public.company c ON c.id=p.company_id
    LEFT JOIN public.career_posting_visibility v ON v.posting_id=p.id AND v.namespace=${namespace()}
  ), matched AS (SELECT * FROM records WHERE state=$1
    AND ($2='' OR strpos(lower(company||' '||title||' '||"postingNo"),lower($2))>0))
  SELECT (SELECT count(*)::int FROM matched) AS total,
    coalesce((SELECT jsonb_agg(row_to_json(page)) FROM
      (SELECT * FROM matched ORDER BY id::bigint DESC LIMIT 20 OFFSET $3) page),'[]'::jsonb) AS items,
    (SELECT jsonb_object_agg(state,n) FROM (SELECT state,count(*)::int AS n FROM records GROUP BY state) counts) AS counts`,
    [status, query, offset],
  );
  return rows[0] as {
    total: number;
    items: PublicationItem[];
    counts: Partial<Record<PublicationStatus, number>>;
  };
}

export async function changePostingPublication(
  db: Database,
  input: { id: string; revision: number; hidden: boolean },
  subject: string,
) {
  // One conditional statement: do not overwrite another admin's decision or
  // publish a posting that is now closed, excluded, or lacks an IT extraction.
  const { rows } = await db.query(
    `WITH target AS (
    SELECT p.id FROM public.posting p WHERE p.id=$1 AND ($3 OR (${eligiblePostingSql("p")}))
  ), updated AS (
    UPDATE public.career_posting_visibility v SET hidden=$3,revision=v.revision+1,changed_by=$4,changed_at=clock_timestamp()
    FROM target p WHERE v.posting_id=p.id AND v.namespace=${namespace()} AND v.revision=$2 RETURNING v.revision
  ), inserted AS (
    INSERT INTO public.career_posting_visibility(namespace,posting_id,hidden,changed_by)
    SELECT ${namespace()},id,$3,$4 FROM target WHERE $2=0
    ON CONFLICT(namespace,posting_id) DO NOTHING RETURNING revision
  ) SELECT revision FROM updated UNION ALL SELECT revision FROM inserted`,
    [input.id, input.revision, input.hidden, subject],
  );
  return rows.length > 0;
}
