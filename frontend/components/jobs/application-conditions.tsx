import { Award, GraduationCap, BriefcaseBusiness, Info } from "lucide-react";
import { demoMyProfile } from "@/mock/hiring-cohort";

export function ApplicationConditions({
  onOpenPosting,
}: {
  onOpenPosting: () => void;
}) {
  const mine = demoMyProfile();
  return (
    <section
      className="application-conditions"
      aria-labelledby="conditions-title"
    >
      <header>
        <h3 id="conditions-title">지원 조건</h3>
        <p>기술 스탯과 별도로 확인해요</p>
      </header>
      <p className="conditions-example-label">내 지원 정보 예시</p>
      <dl className="application-condition-rows">
        <div>
          <dt>
            <Award size={20} aria-hidden="true" />
            자격증
          </dt>
          <dd>
            <span>나</span>
            <strong>{mine.certificates.length}개</strong>
            <button onClick={onOpenPosting}>공고 정보 확인</button>
          </dd>
        </div>
        <div>
          <dt>
            <GraduationCap size={20} aria-hidden="true" />
            평균 학점
          </dt>
          <dd>
            <span>나</span>
            <strong>{mine.gpa.toFixed(1)}</strong>
            <small>/ 4.5</small>
          </dd>
        </div>
        <div>
          <dt>
            <BriefcaseBusiness size={20} aria-hidden="true" />
            경력
          </dt>
          <dd>
            <span>나</span>
            <strong>{mine.career}</strong>
          </dd>
        </div>
      </dl>
      <p className="conditions-footnote">
        <Info size={15} aria-hidden="true" />
        자격증·학점·경력은 기술 LV 점수에 포함하지 않아요.
      </p>
    </section>
  );
}
