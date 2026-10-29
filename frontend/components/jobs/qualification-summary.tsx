import { CheckCircle2, CircleX } from "lucide-react";
import {
  matchingSkills,
  qualificationLabel,
  type JobComparison,
} from "@/lib/study-prototype";

export function QualificationSummary({
  comparison,
}: {
  comparison: JobComparison;
}) {
  const label = qualificationLabel(comparison);
  const Icon = label === "만족" ? CheckCircle2 : CircleX;
  return (
    <div
      className={`qualification-summary ${label === "만족" ? "satisfied" : "unsatisfied"}`}
    >
      <div className="qualification-heading">
        <Icon size={19} />
        <strong>자격요건 {label}</strong>
      </div>
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
    </div>
  );
}
