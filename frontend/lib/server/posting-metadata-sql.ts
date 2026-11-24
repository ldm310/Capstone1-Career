export const koreaTodaySql = "(now() AT TIME ZONE 'Asia/Seoul')::date";
export const openPostingSql = (alias: string) =>
  `${alias}.status='진행' AND (${alias}.deadline IS NULL OR ${alias}.deadline>=${koreaTodaySql}) AND NOT EXISTS (SELECT 1 FROM public.extraction_run excluded_review WHERE excluded_review.posting_id=${alias}.id AND excluded_review.is_current AND excluded_review.review_result='제외')`;
export const closedPostingSql = (alias: string) =>
  `(${alias}.status='마감' OR ${alias}.deadline<${koreaTodaySql})`;
