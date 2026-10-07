import { CheckCircle2, CircleHelp, CircleX } from "lucide-react";
import {
  matchingSkills,
  qualificationLabel,
  type JobComparison,
} from "@/lib/study-prototype";

export function QualificationSummary({
  comparison,
}: {
  comparison?: JobComparison;
}) {
  const label = qualificationLabel(comparison);
  const Icon = !comparison
    ? CircleHelp
    : label === "만족"
      ? CheckCircle2
      : CircleX;
  return (
    <div
      className={`qualification-summary ${!comparison ? "pending" : label === "만족" ? "satisfied" : "unsatisfied"}`}
    >
      <div className="qualification-heading">
        <Icon size={19} />
        <strong>자격요건 {label}</strong>
        {comparison && <small>예시</small>}
      </div>
      {comparison ? (
        <>
          <p>
            우대사항{" "}
            <strong>
              {comparison.preferred.filter((r) => r.satisfied).length}/
              {comparison.preferred.length}개
            </strong>{" "}
            만족
          </p>
          <div className="qualification-skills">
            {matchingSkills(comparison).map((item) => (
              <span key={item.skill}>
                {item.skill} <b>LV{item.level}</b>
              </span>
            ))}
          </div>
        </>
      ) : (
        <>
          <p>우대사항 · 비교 결과 대기</p>
          <span className="qualification-pending-note">
            내 자료와 공고 조건을 확인하면 여기에 표시돼요.
          </span>
        </>
      )}
    </div>
  );
}
