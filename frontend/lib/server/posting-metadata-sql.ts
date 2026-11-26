export const koreaTodaySql = "(now() AT TIME ZONE 'Asia/Seoul')::date";
// Environment-owned namespace, escaped as a SQL literal; never supplied by clients.
export const visibilityNamespaceSql = () =>
  "'" +
  (process.env.CAREER_PROFILE_NAMESPACE || "local-review").replaceAll(
    "'",
    "''",
  ) +
  "'";
export const extractedPostingSql = (alias: string) =>
  `EXISTS (SELECT 1 FROM public.extraction_run visible_run
    JOIN public.recruit_unit visible_unit ON visible_unit.run_id=visible_run.id AND visible_unit.is_it
      AND visible_unit.job IN ('백엔드','데이터 엔지니어')
    JOIN public.unit_item visible_item ON visible_item.unit_id=visible_unit.id
    WHERE visible_run.posting_id=${alias}.id AND visible_run.is_current
      AND visible_item.category IN ('업무','필수','우대','기타') AND length(trim(visible_item.text))>0)`;
export const eligiblePostingSql = (alias: string) =>
  `${alias}.status='진행' AND (${alias}.deadline IS NULL OR ${alias}.deadline>=${koreaTodaySql}) AND ${extractedPostingSql(alias)} AND NOT EXISTS (SELECT 1 FROM public.extraction_run excluded_review WHERE excluded_review.posting_id=${alias}.id AND excluded_review.is_current AND excluded_review.review_result='제외')`;
export const openPostingSql = (alias: string) =>
  `${eligiblePostingSql(alias)} AND NOT EXISTS (SELECT 1 FROM public.career_posting_visibility visibility WHERE visibility.posting_id=${alias}.id AND visibility.namespace=${visibilityNamespaceSql()} AND visibility.hidden)`;
export const closedPostingSql = (alias: string) =>
  `(${alias}.status='마감' OR ${alias}.deadline<${koreaTodaySql})`;
