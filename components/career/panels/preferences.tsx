"use client";
import type { PanelProps } from "./types";
import { day } from "@/lib/workspace-selectors";
export function PreferencesPanel({
  state,
  busy,
  save,
}: Pick<PanelProps, "state" | "busy" | "save">) {
  return (
    <section className="career-panel">
      <h2>어떤 직무를 준비하고 있나요?</h2>
      <p>
        목표 직무를 선택하세요. 지역이나 준비 일정은 나중에 입력해도 괜찮아요.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          await save("preferences", {
            role: f.get("role"),
            region: f.get("region"),
            experience: f.get("experience"),
            hours: Number(f.get("hours")),
            targetDate: f.get("targetDate"),
          });
        }}
      >
        <div className="career-two">
          <label>
            목표 직무
            <select name="role" defaultValue={state.role}>
              <option value="ax">AX·LLM 개발자</option>
              <option value="ml">AI·ML 엔지니어</option>
              <option value="data">데이터 엔지니어</option>
            </select>
          </label>
          <details>
            <summary>지역·준비 시간 추가하기 (선택)</summary>
            <label>
              희망 지역
              <input
                name="region"
                defaultValue={state.region}
                placeholder="예: 서울 / 비우면 전체"
              />
            </label>
            <label>
              경력·준비 상황
              <input
                name="experience"
                defaultValue={state.experience}
                placeholder="예: 신입 / 백엔드 2년"
              />
            </label>
            <label>
              주당 준비 시간
              <input
                name="hours"
                type="number"
                min={1}
                max={60}
                defaultValue={state.hours}
              />
            </label>
            <label>
              목표 지원일
              <input
                name="targetDate"
                type="date"
                min={day()}
                defaultValue={state.targetDate}
              />
            </label>
          </details>
        </div>
        <button disabled={busy}>준비 조건 저장</button>
      </form>
    </section>
  );
}
