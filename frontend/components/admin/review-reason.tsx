export function ReviewReason({ reason }: { reason: Record<string, unknown> }) {
  const text = String(
    reason["내용"] || reason.message || "검토 사유 확인 필요",
  );
  const roles = text.match(
    /^모집 직무 칸 (\d+)개\s*\/\s*만든 자리 이름 (\d+)개$/,
  );
  if (roles)
    return (
      <>
        <strong>모집 직무 구분 확인 필요</strong>
        <p>
          모집부문 제목 감지 {roles[1]}회, 추출된 고유 직무명 {roles[2]}개
        </p>
        <p>
          모집부문 제목이 반복됐거나 직무가 누락됐을 수 있습니다. 원문의 실제
          모집 직무와 추출 결과를 비교해 주세요.
        </p>
      </>
    );

  const career = text.match(/^경력 조건 '(.+)'\s*\/\s*만든 자리 경력:\s*(.*)$/);
  if (career)
    return (
      <>
        <strong>경력 조건 확인 필요</strong>
        <p>
          공고의 경력 조건: {career[1]}, 추출된 경력 구분: {career[2] || "없음"}
        </p>
        <p>신입과 경력 중 빠진 모집 대상이 있는지 원문과 비교해 주세요.</p>
      </>
    );

  const empty = text.match(/^IT 자리 '(.+)'의 필수·우대·업무가 비어 있음$/);
  if (empty)
    return (
      <>
        <strong>직무별 추출 내용 확인 필요</strong>
        <p>‘{empty[1]}’의 자격요건, 우대사항, 담당업무가 모두 비어 있습니다.</p>
        <p>원문에 해당 내용이 없는지, 추출 과정에서 빠졌는지 확인해 주세요.</p>
      </>
    );

  return (
    <>
      <strong>검토 사유 확인</strong>
      <p>{text}</p>
    </>
  );
}
