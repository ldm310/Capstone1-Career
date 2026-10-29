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
      <h2>준비 조건</h2>
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
              <option value="data">데이터</option>
              <option value="backend">백엔드</option>
            </select>
          </label>
          <details>
            <summary>지역, 준비 시간 (선택)</summary>
            <label>
              희망 지역
              <input
                name="region"
                defaultValue={state.region}
                placeholder="예: 서울"
              />
            </label>
            <label>
              경력
              <input
                name="experience"
                defaultValue={state.experience}
                placeholder="예: 신입"
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
        <button disabled={busy}>저장</button>
      </form>
    </section>
  );
}
