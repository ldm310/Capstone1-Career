export function ReviewReason({ reason }: { reason: Record<string, unknown> }) {
  const text = String(
    reason["내용"] || reason.message || "검토 사유 확인 필요",
  );
  const roles = text.match(
    /^모집 직무 칸 (\d+)개\s*\/\s*만든 자리 이름 (\d+)개$/,
  );
  if (roles)
    return <strong>모집 직무 구분 확인 필요</strong>;

  const career = text.match(/^경력 조건 '(.+)'\s*\/\s*만든 자리 경력:\s*(.*)$/);
  if (career)
    return <strong>경력 조건 확인 필요</strong>;

  const empty = text.match(/^IT 자리 '(.+)'의 필수·우대·업무가 비어 있음$/);
  if (empty)
    return <strong>직무별 추출 내용 확인 필요</strong>;

  return <strong>검토 사유 확인</strong>;
}
