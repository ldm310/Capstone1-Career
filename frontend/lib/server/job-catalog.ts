import type { Pool, PoolClient } from "pg";
import type { PublicJob } from "@/types/public-job";
import { openPostingSql } from "./posting-metadata-sql";
import { postingMetadata } from "./posting-metadata";
import {
  workplaceKey,
  jobExperience,
  type ExperienceKind,
} from "@/lib/job-filters";

export type CatalogQuery = {
  query: string;
  role: string;
  location: string;
  workplace: string;
  experience: ExperienceKind[];
  sort: string;
  offset: number;
  limit: number;
};
function matches(job: PublicJob, input: CatalogQuery) {
  return (
    (input.role === "all" || job.category === input.role) &&
    !job.dummy &&
    (!job.closesAt || Date.parse(job.closesAt) >= Date.now()) &&
    (!input.location ||
      (input.location === "unknown"
        ? job.location === "근무지 원문 확인"
        : job.location.toLowerCase().includes(input.location))) &&
    (input.workplace === "all" ||
      workplaceKey(job.workplace) === input.workplace) &&
    (!input.experience.length ||
      input.experience.some((value) => jobExperience(job).includes(value))) &&
    `${job.company} ${job.title} ${(job.skills || []).join(" ")}`
      .toLowerCase()
      .includes(input.query)
  );
}

// Search/count all postings in one read-only statement; fetch only one light page.
// Full extraction trees remain on the existing Spring detail endpoint.
export async function searchJobCatalog(
  db: Pick<Pool | PoolClient, "query">,
  input: CatalogQuery,
  external: PublicJob[],
): Promise<{ jobs: PublicJob[]; total: number; nextOffset: number | null }> {
  const result = await db.query(
    `
    WITH base AS (
      SELECT p.*,c.name AS company,e.id AS run_id,
        CASE
          WHEN p.title ~* '\\mdata[[:space:]]+(engineer|analyst|scientist|platform)|데이터[[:space:]]*(엔지니어|분석|사이언|플랫폼|개발)' THEN 'data'
          WHEN p.title ~* 'back[ -]?end|백엔드|서버[[:space:]]*(개발|엔지니어)|server[ -]?side' THEN 'backend'
          WHEN coalesce(p.site_job_category,'') ~ '데이터' THEN 'data'
          WHEN coalesce(p.site_job_category,'') ~ '백엔드|서버' THEN 'backend'
        END AS role,
        concat_ws(' ',p.career_condition,(SELECT string_agg(u.career,' ') FROM public.recruit_unit u WHERE u.run_id=e.id)) AS careers
      FROM public.posting p JOIN public.company c ON c.id=p.company_id
      LEFT JOIN public.extraction_run e ON e.posting_id=p.id AND e.is_current
      WHERE ${openPostingSql("p")}
    ), metadata AS MATERIALIZED (
      SELECT b.*,m.location AS actual_location,m.workplace AS actual_workplace
      FROM base b LEFT JOIN jsonb_to_recordset($10::jsonb) AS m(id bigint,location text,workplace text) ON m.id=b.id
      WHERE b.role IS NOT NULL
    ), career_flags AS (
      SELECT *,array_remove(ARRAY[
        CASE WHEN careers ~ '무관' THEN 'any' END,
        CASE WHEN careers ~ '신입' OR min_years=0 THEN 'entry' END,
        CASE WHEN regexp_replace(careers,'경력[[:space:]]*무관','','g') ~ '경력' THEN 'experienced' END,
        CASE WHEN concat_ws(' ',employment_type,title) ~ '인턴' THEN 'intern' END
      ],NULL) AS declared_experience FROM metadata
    ), classified AS (
      SELECT *,CASE WHEN cardinality(declared_experience)>0 THEN declared_experience ELSE array_remove(ARRAY[
        CASE WHEN concat_ws(' ',title,employment_type) ~* '경력[[:space:]]*무관|신입[[:space:]]*[/·][[:space:]]*경력' THEN 'any' END,
        CASE WHEN concat_ws(' ',title,employment_type) ~* '신입|entry.?level|new.?grad' THEN 'entry' END,
        CASE WHEN concat_ws(' ',title,employment_type) ~* '경력(?![[:space:]]*무관)|senior|staff|principal' THEN 'experienced' END,
        CASE WHEN concat_ws(' ',title,employment_type) ~* '인턴|\\mintern\\M|internship' THEN 'intern' END
      ],NULL) END AS experience FROM career_flags
    ), backend AS (
      SELECT jsonb_build_object(
        'id','be:' || p.id,'company',p.company,'title',p.title,'category',p.role,
        'location',coalesce(p.actual_location,'근무지 원문 확인'),'employment',coalesce(nullif(p.employment_type,''),'고용 형태 원문 확인'),
        'workplace',p.actual_workplace,'postedAt',p.collected_at,
        'closesAt',CASE WHEN p.deadline IS NOT NULL THEN to_char(p.deadline,'YYYY-MM-DD') || 'T23:59:59+09:00' END,
        'experience',p.experience,
        'url',CASE WHEN p.site IN ('사람인','saramin') THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=' || p.site_posting_no ELSE '' END
      ) AS job,p.run_id
      FROM classified p
      WHERE p.role IS NOT NULL AND ($2='all' OR p.role=$2)
        AND ($3='' OR ($3='unknown' AND p.actual_location IS NULL) OR ($3<>'unknown' AND strpos(lower(p.actual_location),$3)>0))
        AND ($4='all' OR ($4='unknown' AND p.actual_workplace IS NULL) OR ($4='remote' AND p.actual_workplace='원격 근무') OR ($4='hybrid' AND p.actual_workplace='하이브리드 근무') OR ($4='on-site' AND p.actual_workplace='사무실 근무'))
        AND (cardinality($5::text[])=0 OR p.experience && $5::text[])
        AND ($1='' OR strpos(lower(p.company || ' ' || p.title),$1)>0 OR EXISTS (
          SELECT 1 FROM public.recruit_unit u JOIN public.unit_item i ON i.unit_id=u.id
          JOIN public.requirement r ON r.item_id=i.id
          JOIN public.requirement_tech rt ON rt.requirement_id=r.id
          LEFT JOIN public.tech t ON t.id=rt.tech_id
          WHERE u.run_id=p.run_id AND strpos(lower(coalesce(t.name,rt.written_name)),$1)>0
        ))
    ), real AS (
      SELECT * FROM backend
      UNION ALL SELECT value,NULL::bigint FROM jsonb_array_elements($9::jsonb)
    ), eligible AS (
      SELECT * FROM real
    ), page AS (
      SELECT *,row_number() OVER (ORDER BY
        CASE WHEN $6='closing' THEN (job->>'closesAt')::timestamptz END ASC NULLS LAST,
        CASE WHEN $6='company' THEN lower(job->>'company') END COLLATE "C" ASC NULLS LAST,
        CASE WHEN $6='newest' THEN (job->>'postedAt')::timestamptz END DESC NULLS LAST,
        (job->>'id') COLLATE "C" DESC
      ) AS position FROM eligible
      ORDER BY position LIMIT $8 OFFSET $7
    ), enriched AS (
      SELECT position,CASE WHEN job->>'id' LIKE 'be:%' THEN job || jsonb_build_object('skills',coalesce((
        SELECT jsonb_agg(name ORDER BY name COLLATE "C") FROM (
          SELECT DISTINCT coalesce(t.name,rt.written_name) AS name
          FROM public.recruit_unit u JOIN public.unit_item i ON i.unit_id=u.id
          JOIN public.requirement r ON r.item_id=i.id
          JOIN public.requirement_tech rt ON rt.requirement_id=r.id
          LEFT JOIN public.tech t ON t.id=rt.tech_id WHERE u.run_id=page.run_id
        ) skills
      ),'[]'::jsonb)) ELSE job END AS job FROM page
    )
    SELECT (SELECT count(*)::int FROM eligible) AS total,
      coalesce((SELECT jsonb_agg(job ORDER BY position) FROM enriched),'[]'::jsonb) AS jobs
  `,
    [
      input.query,
      input.role,
      input.location,
      input.workplace,
      input.experience,
      input.sort,
      input.offset,
      input.limit,
      JSON.stringify(external.filter((job) => matches(job, input))),
      JSON.stringify(await postingMetadata(db)),
    ],
  );
  const { jobs, total } = result.rows[0] as {
    jobs: PublicJob[];
    total: number;
  };
  return {
    jobs,
    total,
    nextOffset:
      input.offset + input.limit < total ? input.offset + input.limit : null,
  };
}
