"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { LearningPath } from "./learning-path";
import { DetailDialog } from "./detail-dialog";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  GitBranch,
  Trophy,
  BookOpen,
  CircleHelp,
} from "lucide-react";
import {
  criteria,
  levelNames,
  rewards,
  requirement,
  denseRanking,
} from "@/lib/growth/catalog";
import {
  emptyGrowth,
  type GrowthState,
  type Level,
  type RankingRow,
} from "@/types/growth";
import type { Finding } from "@/types/workspace";
import { mergeReviews } from "@/lib/growth/model";
import { sample } from "@/mock/growth";
export function GrowthHub({
  demo = false,
  preparation = false,
  role = "ax",
  view = "overview",
  findings = [],
  targets = ["Docker", "Python", "RAG", "Vector DB", "LangGraph"],
  onSources,
}: {
  demo?: boolean;
  preparation?: boolean;
  role?: string;
  view?: string;
  findings?: Finding[];
  targets?: string[];
  onSources?: () => void;
}) {
  const [g, setG] = useState<GrowthState>(
    demo ? structuredClone(sample) : structuredClone(emptyGrowth),
  );
  const [ranking, setRanking] = useState<RankingRow[]>([]),
    [userId, setUserId] = useState("sample-me");
  const [loading, setLoading] = useState(!demo),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [selected, setSelected] = useState<string | null>(null),
    [filter, setFilter] = useState("all"),
    [demoStep, setDemoStep] = useState(0),
    [demoRole, setDemoRole] = useState("ax");
  useEffect(() => {
    if (demo) return;
    let active = true;
    fetch("/api/growth")
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.error);
        if (active) {
          setG(d.growth);
          setRanking(d.ranking);
          setUserId(d.userId);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [demo, findings]);
  useEffect(() => {
    if (!demo) return;
    try {
      const role = sessionStorage.getItem("career-growth-sample-role");
      if (role) queueMicrotask(() => setDemoRole(role));
      const saved = sessionStorage.getItem("career-growth-sample-v1");
      if (saved) {
        const restored: GrowthState = JSON.parse(saved);
        queueMicrotask(() => setG(restored));
      }
    } catch {
      /* A fresh sample is safe if browser storage is unavailable. */
    }
  }, [demo]);
  async function act(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (demo) {
        const next = structuredClone(g);
        const skill = String(body.skill);
        if (body.action === "review") {
          const r = next.reviews.find((r) => r.skill === skill);
          if (r) {
            r.status = body.status as typeof r.status;
            if (body.status === "edited") {
              r.skill = String(body.name);
              r.level = null;
            }
          }
        }
        if (
          body.action === "start" &&
          !next.tasks.some((t) => t.skill === skill && t.level === body.level)
        ) {
          const level = body.level as Level;
          next.tasks.push({
            id: crypto.randomUUID(),
            skill,
            level,
            reward: rewards[level],
            baseline:
              next.reviews.find((r) => r.skill === skill)?.level || null,
            baselineEvidence: [],
            startedAt: new Date().toISOString(),
            date: "",
            status: "active",
            submissions: [],
          });
        }
        if (body.action === "submit") {
          const t = next.tasks.find((t) => t.id === body.id);
          if (t && t.status !== "completed") {
            t.status = "completed";
            t.submissions.push({
              at: new Date().toISOString(),
              evidence: String(body.evidence),
              explanation: String(body.explanation),
              feedback:
                "샘플 검토 결과: 필수 조건을 모두 확인한 경우의 예시예요. 실제 자료를 검증한 결과가 아니에요.",
            });
            next.rewards.push({
              id: crypto.randomUUID(),
              taskId: t.id,
              skill: t.skill,
              level: t.level,
              points: t.reward,
              at: new Date().toISOString(),
              reason: "샘플 과제 완료",
            });
            const r = next.reviews.find((r) => r.skill === t.skill);
            if (r) {
              r.level = t.level;
              r.reason = "샘플 과제의 필수 조건을 충족한 결과 예시예요.";
            } else
              next.reviews.push({
                skill: t.skill,
                original: t.skill,
                level: t.level,
                status: "confirmed",
                reason: "샘플 과제 완료 예시",
                evidenceIds: [],
              });
          }
        }
        if (body.action === "date") {
          const t = next.tasks.find((t) => t.id === body.id);
          if (t) t.date = String(body.date);
        }
        if (body.action === "settings") {
          next.nickname = String(body.nickname);
          next.publicRanking = Boolean(body.publicRanking);
        }
        setG(next);
        try {
          sessionStorage.setItem(
            "career-growth-sample-v1",
            JSON.stringify(next),
          );
        } catch {
          /* Sample remains available for this visit. */
        }
        setMessage("샘플 화면에 반영했어요. 실제 기록에는 영향을 주지 않아요.");
      } else {
        const r = await fetch("/api/growth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json();
        if (!r.ok) throw Error(d.error);
        setG(d.growth);
        setRanking(d.ranking);
        setMessage("변경 내용을 저장했어요.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }
  const growth = mergeReviews(g, findings),
    visible = growth.reviews.filter((r) => r.status !== "excluded"),
    points = g.rewards.reduce((s, r) => s + r.points, 0);
  const names = [
    ...new Set([
      ...visible.map((r) => r.skill),
      ...(demo
        ? {
            ax: ["Docker", "Python", "RAG", "Vector DB", "LangGraph"],
            ml: ["Python", "PyTorch", "Docker"],
            data: ["SQL", "PostgreSQL", "Airflow", "Spark"],
          }[demoRole] || targets
        : targets
      ).filter(
        (s) =>
          !growth.reviews.some((r) => r.skill === s && r.status === "excluded"),
      ),
    ]),
  ];
  const rows = demo
    ? denseRanking([
        {
          id: "sample-a",
          nickname: "꾸준한 구름 · 예시",
          points: 60,
          completed: 3,
        },
        {
          id: "sample-b",
          nickname: "푸른 하늘 · 예시",
          points: 60,
          completed: 3,
        },
        ...(g.publicRanking
          ? [
              {
                id: userId,
                nickname: g.nickname,
                points,
                completed: g.rewards.length,
              },
            ]
          : []),
      ])
    : ranking;
  const pending = visible.filter((r) => r.status === "pending").length;
  if (loading) return <p role="status">내 성장 기록을 불러오고 있어요…</p>;
  return (
    <div className="growth-hub">
      {demo && (
        <h1>
          {view === "skills"
            ? "내 기술과 다음 단계"
            : view === "tasks"
              ? "단계별 과제"
              : view === "start"
                ? "자료 하나로 시작하는 Career"
                : "나의 성장 대시보드"}
        </h1>
      )}
      {demo && (
        <div className="growth-demo">
          <strong>샘플 체험</strong>
          <span>
            예시 자료로 둘러보세요. 포인트·순위는 실제 계정과 분리돼요.
          </span>
          <button
            onClick={() => {
              setG(structuredClone(sample));
              sessionStorage.removeItem("career-growth-sample-v1");
              setDemoStep(0);
              setMessage("샘플을 초기화했어요.");
            }}
          >
            초기화
          </button>
          <Link href="/growth">내 자료로 시작</Link>
          <Link href="/">체험 종료</Link>
        </div>
      )}
      <div aria-live="polite">
        {message && <p className="career-status">{message}</p>}
        {error && (
          <p role="alert" className="career-error">
            {error}{" "}
            <button onClick={() => window.location.reload()}>
              다시 불러오기
            </button>
          </p>
        )}
      </div>
      {["overview", "start", "summary"].includes(view) && (
        <>
          <section className="growth-welcome">
            <span className="live-label">
              {view === "summary" ? "나의 성장 기록" : "나의 준비 현황"}
            </span>
            <h2>
              {view === "summary"
                ? "준비하며 쌓은 변화를 확인하세요."
                : visible.length
                  ? "해온 것을 확인하고, 다음 단계를 준비해요."
                  : "내 경험에서, 다음 준비를 찾으세요."}
            </h2>
            <p>
              자료에서 내 기술을 확인하고, 원하는 직무에 필요한 부분을 하나씩
              채워가세요.
            </p>
            {view !== "summary" && (
              <ol className="growth-steps">
                {["목표 선택", "자료 추가", "결과 확인", "준비 시작"].map(
                  (s, i) => (
                    <li key={s}>
                      <span>{i + 1}</span>
                      {s}
                    </li>
                  ),
                )}
              </ol>
            )}
            {demo && view === "start" && demoStep < 2 ? (
              <div className="growth-demo-step">
                {demoStep === 0 ? (
                  <>
                    <h3>어떤 직무를 준비하고 있나요?</h3>
                    <label>
                      희망 직무
                      <select
                        value={demoRole}
                        onChange={(e) => {
                          setDemoRole(e.target.value);
                          sessionStorage.setItem(
                            "career-growth-sample-role",
                            e.target.value,
                          );
                        }}
                      >
                        <option value="ax">AX / LLM 엔지니어</option>
                        <option value="ml">AI / ML 엔지니어</option>
                        <option value="data">데이터 엔지니어</option>
                      </select>
                    </label>
                    <button onClick={() => setDemoStep(1)}>
                      이 직무로 시작하기 <ArrowRight size={16} />
                    </button>
                  </>
                ) : (
                  <>
                    <h3>지금까지 해온 것을 알려주세요</h3>
                    <p>
                      자료 하나로 시작할 수 있어요. 체험에서는 준비된 예시를
                      사용해요.
                    </p>
                    <div className="growth-source-options">
                      {[
                        ["GitHub 링크", GitBranch],
                        ["PDF · 이력서·포트폴리오", FileText],
                        ["Markdown · 학습 노트", BookOpen],
                      ].map(([label, Icon]) => {
                        const I = Icon as typeof GitBranch;
                        return (
                          <button
                            key={String(label)}
                            onClick={() => {
                              setDemoStep(2);
                              setMessage(
                                "예시 분석 결과를 준비했어요. 아래에서 기술과 근거를 확인해 주세요.",
                              );
                            }}
                          >
                            <I size={22} />
                            {String(label)}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            ) : !demo && !findings.length && view !== "summary" ? (
              <button onClick={onSources}>
                자료 하나로 시작하기 <ArrowRight size={17} />
              </button>
            ) : null}
            <div className="growth-stats">
              <div>
                <strong>{visible.length}</strong>
                <span>자료에서 찾은 기술</span>
              </div>
              <div>
                <strong>{pending}</strong>
                <span>확인할 결과</span>
              </div>
              <div>
                <strong>
                  {points}
                  <small>점</small>
                </strong>
                <span>성장 포인트</span>
              </div>
            </div>
            <small>
              기존 자료에서 인정된 수준에는 포인트가 없어요. 부족한 부분을
              보완한 과제에만 지급돼요.
            </small>
          </section>
        </>
      )}
      {preparation && view === "skills" && (
        <LearningPath
          role={role}
          reviews={visible}
          tasks={g.tasks}
          onSelect={setSelected}
        />
      )}
      {["overview", "skills", "start"].includes(view) &&
        !(demo && view === "start" && demoStep < 2) && (
          <section className="career-panel">
            <div className="growth-section-heading">
              <div>
                <h2>
                  {preparation
                    ? "내 기술에 맞는 다음 과제"
                    : pending
                      ? "자료에서 이런 기술을 찾았어요"
                      : "기술별 다음 단계"}
                </h2>
                <p>
                  현재 수준과 다음 과제를 함께 확인하세요. 틀린 항목만 수정하면
                  돼요.
                </p>
              </div>
              <label>
                보기
                <select
                  aria-label="보기"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">모든 기술</option>
                  <option value="pending">확인할 결과</option>
                  <option value="unknown">자료 부족</option>
                  {[1, 2, 3].map((n) => (
                    <option key={n} value={String(n)}>
                      LV{n}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="growth-cards">
              {names
                .filter((s) => {
                  const r = visible.find((r) => r.skill === s);
                  return (
                    filter === "all" ||
                    (filter === "pending"
                      ? r?.status === "pending"
                      : filter === "unknown"
                        ? !r?.level
                        : String(r?.level) === filter)
                  );
                })
                .slice(0, view === "overview" ? 4 : undefined)
                .map((skill) => {
                  const r = visible.find((r) => r.skill === skill);
                  const next = ((r?.level || 0) + 1) as Level;
                  return (
                    <article className="growth-skill" key={skill}>
                      <div className="growth-section-heading">
                        <h3>{skill}</h3>
                        <span className="growth-tag">
                          {r?.status === "pending"
                            ? "확인 전"
                            : r?.status === "edited"
                              ? "사용자 수정"
                              : r?.status === "appeal"
                                ? "추가 검토 필요"
                                : r?.status === "confirmed"
                                  ? "결과 확인함"
                                  : "자료 미확인"}
                        </span>
                      </div>
                      <p className="growth-current">
                        현재 수준
                        <br />
                        <strong>
                          {r?.level
                            ? `LV${r.level} · ${levelNames[r.level]}`
                            : "확인할 자료가 부족해요"}
                        </strong>
                      </p>
                      <div className="growth-levels">
                        {([1, 2, 3] as Level[]).map((l) => (
                          <span
                            key={l}
                            className={(r?.level || 0) >= l ? "met" : ""}
                          >
                            LV{l}
                            <small>{levelNames[l]}</small>
                          </span>
                        ))}
                      </div>
                      <p>
                        {r?.reason ||
                          "못한다는 뜻이 아니에요. 관련 자료를 추가하면 확인할 수 있어요."}
                      </p>
                      <div className="growth-next">
                        <small>다음 준비</small>
                        <strong>
                          {next <= 3 && criteria[skill]
                            ? `LV${next} · ${levelNames[next]}`
                            : r?.level === 3
                              ? "확인된 역량을 공고와 비교해 보세요"
                              : "평가 기준 준비 중"}
                        </strong>
                        {next <= 3 && criteria[skill] && (
                          <span>완료 확인 후 {rewards[next]}점</span>
                        )}
                      </div>
                      <button onClick={() => setSelected(skill)}>
                        근거·과제 확인하기 <ArrowRight size={16} />
                      </button>
                    </article>
                  );
                })}
            </div>
            {view === "overview" && names.length > 4 && (
              <Link href={demo ? "/skills" : "/my-skills?tab=skills"}>
                내 기술 전체 보기 ({names.length}) →
              </Link>
            )}
            {!names.length && (
              <p>자료를 추가하면 기술별 준비 경로가 여기에 나타나요.</p>
            )}
          </section>
        )}
      {demo && view === "start" && demoStep === 2 && (
        <Link className="career-primary" href="/dashboard">
          내 성장 화면으로 이동하기 →
        </Link>
      )}
      {["overview", "tasks", "plan"].includes(view) && (
        <section className="career-panel">
          <h2>진행 중인 과제</h2>
          <p>
            완료 기준을 확인하고 새 작업의 근거를 제출하세요. 일정 체크만으로
            보상되지는 않아요.
          </p>
          {!g.tasks.length ? (
            <p className="growth-empty">
              아직 시작한 과제가 없어요.{" "}
              <Link href={demo ? "/skills" : "/my-skills?tab=skills"}>
                내 기술에서 다음 과제 선택하기 →
              </Link>
            </p>
          ) : (
            g.tasks.map((t) => (
              <article key={t.id} className="growth-task">
                <div className="growth-section-heading">
                  <h3>
                    {t.skill} · LV{t.level} {levelNames[t.level]}
                  </h3>
                  <span className="growth-tag">
                    {t.status === "completed"
                      ? "완료 확인"
                      : t.status === "needs_evidence"
                        ? "검증 기능 연결 필요"
                        : "진행 중"}
                  </span>
                </div>
                <p>{requirement(t.skill, t.level)}</p>
                <small>
                  시작 시 고정된 보상 {t.reward}점 ·{" "}
                  {new Date(t.startedAt).toLocaleDateString("ko-KR")} 시작
                </small>
                <label>
                  나의 목표일
                  <input
                    type="date"
                    aria-label={`${t.skill} 목표일`}
                    value={t.date}
                    onChange={(e) => {
                      if (e.target.value)
                        void act({
                          action: "date",
                          id: t.id,
                          date: e.target.value,
                        });
                    }}
                  />
                </label>
                {t.status !== "completed" && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      void act({
                        action: "submit",
                        id: t.id,
                        evidence: f.get("evidence"),
                        explanation: f.get("explanation"),
                      });
                    }}
                  >
                    <label>
                      새 작업의 근거
                      <input
                        name="evidence"
                        required
                        minLength={5}
                        maxLength={2000}
                        placeholder="GitHub 커밋 링크 또는 업로드한 자료의 이름"
                      />
                    </label>
                    <label>
                      무엇을 새로 구현했나요?
                      <textarea
                        name="explanation"
                        required
                        minLength={10}
                        maxLength={10000}
                        placeholder="완료 기준별 변경 내용, 실행 방법과 결과를 설명해 주세요."
                      />
                    </label>
                    <p>
                      {demo
                        ? "샘플에서는 제출 후 완료 결과와 보상 화면을 체험할 수 있어요."
                        : "현재는 제출 내용 보관까지 지원해요. 자동 완료 검증이 연결되기 전에는 수준·포인트가 변경되지 않아요."}
                    </p>
                    <button disabled={busy}>
                      {demo ? "샘플 완료 결과 보기" : "완료 근거 제출하기"}
                    </button>
                  </form>
                )}
                <details>
                  <summary>제출·검토 이력 ({t.submissions.length})</summary>
                  {t.submissions.map((s, i) => (
                    <div key={i}>
                      <time>{new Date(s.at).toLocaleString("ko-KR")}</time>
                      <p>{s.evidence}</p>
                      <p>{s.explanation}</p>
                      <p>{s.feedback}</p>
                    </div>
                  ))}
                </details>
              </article>
            ))
          )}
        </section>
      )}
      {["overview", "summary", "history"].includes(view) && (
        <section className="career-panel">
          <h2>최근 성장 기록</h2>
          <p>
            최신 분석 결과와 이미 완료한 과제·포인트 기록은 별도로 보관해요.
          </p>
          {!g.rewards.length ? (
            <p className="growth-empty">
              아직 받은 포인트가 없어요. LV1 10점 · LV2 20점 · LV3 30점
            </p>
          ) : (
            g.rewards.map((r) => (
              <div className="career-row" key={r.id}>
                <CheckCircle2 size={19} />
                <strong>
                  {r.skill} LV{r.level} 과제 완료
                </strong>
                <span>+{r.points}점</span>
                <time>{new Date(r.at).toLocaleDateString("ko-KR")}</time>
              </div>
            ))
          )}
        </section>
      )}
      {["overview", "summary", "ranking"].includes(view) && (
        <section className="career-panel">
          <h2>
            <Trophy size={20} /> 성장 포인트 랭킹
          </h2>
          <p>
            부족한 역량을 보완한 과제로 쌓은 포인트예요. 실력이나 취업 가능성을
            평가한 순위가 아니에요.
          </p>
          <p>
            {g.publicRanking
              ? `내 순위: ${rows.find((r) => r.id === userId)?.rank || "—"}위`
              : "랭킹 미참여"}{" "}
            · 내 포인트 {points}점
          </p>
          <div className="growth-ranking">
            {rows.length ? (
              rows.map((r) => (
                <div key={r.id} className={r.id === userId ? "mine" : ""}>
                  <strong>{r.rank}위</strong>
                  <span>
                    {r.nickname}
                    {r.id === userId ? " (나)" : ""}
                    <small>완료한 단계 {r.completed}개</small>
                  </span>
                  <b>{r.points}점</b>
                </div>
              ))
            ) : (
              <p>
                아직 공개 참여자가 없어요. 참여 여부는 아래에서 선택할 수
                있어요.
              </p>
            )}
          </div>
          <details>
            <summary>랭킹 참여·공개 설정</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void act({
                  action: "settings",
                  nickname: f.get("nickname"),
                  publicRanking: f.get("public") === "on",
                });
              }}
            >
              <label>
                공개 닉네임
                <input
                  name="nickname"
                  required
                  maxLength={30}
                  defaultValue={g.nickname}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  name="public"
                  defaultChecked={g.publicRanking}
                />{" "}
                랭킹에 공개 참여하기
              </label>
              <small>
                닉네임·포인트·완료 단계 수만 공개돼요. 이메일·자료·포트폴리오는
                공개되지 않아요. 미참여자는 순위 계산에서 제외하며 동점은
                1·1·2위예요.
              </small>
              <button disabled={busy}>공개 설정 저장</button>
            </form>
          </details>
        </section>
      )}
      {selected && (
        <DetailDialog onClose={() => setSelected(null)}>
          <section className="career-panel" aria-label={`${selected} 상세`}>
            <button className="growth-close" onClick={() => setSelected(null)}>
              상세 닫기 ×
            </button>
            <span className="live-label">기술과 다음 준비</span>
            <h2>{selected}</h2>
            {(() => {
              const r = visible.find((r) => r.skill === selected),
                next = ((r?.level || 0) + 1) as Level;
              return (
                <>
                  <p>
                    자료에 쓰인 이름: {r?.original || selected} → 표시 이름:{" "}
                    {selected}
                  </p>
                  <p>
                    {r?.reason || "추가 자료로 현재 수준을 확인할 수 있어요."}
                  </p>
                  {r && (
                    <>
                      <div className="growth-actions">
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "confirmed",
                            })
                          }
                        >
                          결과 확인했어요
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => {
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "excluded",
                            });
                            setSelected(null);
                          }}
                        >
                          관련 없는 기술 제외
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act({
                              action: "review",
                              skill: selected,
                              name: selected,
                              status: "appeal",
                            })
                          }
                        >
                          수준 다시 검토 요청
                        </button>
                      </div>
                      <label>
                        다른 기술로 수정
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) {
                              void act({
                                action: "review",
                                skill: selected,
                                name: e.target.value,
                                status: "edited",
                              });
                              setSelected(null);
                            }
                          }}
                        >
                          <option value="" disabled>
                            기술 선택
                          </option>
                          {Object.keys(criteria).map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </label>
                      <small>
                        이름 수정이나 결과 확인만으로 수준이 검증되거나 포인트가
                        지급되지는 않아요.
                      </small>
                    </>
                  )}
                  <h3>어디에서 찾았나요?</h3>
                  {findings
                    .filter((f) => r?.evidenceIds.includes(f.id))
                    .map((f) => (
                      <div key={f.id}>
                        <p>{f.title}</p>
                        <pre>{f.quote}</pre>
                        <a href={f.url} target="_blank" rel="noreferrer">
                          원문에서 확인 ↗
                        </a>
                      </div>
                    ))}
                  {demo && (
                    <p>
                      샘플 프로젝트의 설정 파일·실행 기록을 사용한 예시예요.
                    </p>
                  )}
                  {!demo && <Link href="/my-skills">추가 자료 올리기 →</Link>}
                  <h3>단계별 완료 기준</h3>
                  <p>
                    Career에서 정의한 기준이에요. 같은 기술의 하위 필수 조건도
                    함께 확인해요.
                  </p>
                  {([1, 2, 3] as Level[]).map((l) => (
                    <div className="growth-criterion" key={l}>
                      <strong>
                        LV{l} · {levelNames[l]}
                      </strong>
                      <p>{requirement(selected, l)}</p>
                      <small>
                        {(r?.level || 0) >= l
                          ? "기존 역량으로 확인한 단계 · 소급 보상 없음"
                          : `해당 과제의 완료 확인 후 ${rewards[l]}점`}
                      </small>
                    </div>
                  ))}
                  <h3>제출할 자료</h3>
                  <p>
                    변경한 코드·설정, 재현 가능한 실행 방법, 실행 결과와 각
                    조건을 충족한 설명을 준비해 주세요. 과거 자료를 뒤늦게
                    추가한 경우에는 성장 보상이 없어요.
                  </p>
                  <p>
                    <CircleHelp size={16} /> 필수 조건에 대한 근거가 빠지면
                    보완이 필요해요. 현재 수준과 과제 난이도는 별개예요.
                  </p>
                  {next <= 3 && criteria[selected] && (
                    <button
                      disabled={
                        busy ||
                        g.tasks.some(
                          (t) => t.skill === selected && t.level === next,
                        )
                      }
                      onClick={() =>
                        void act({
                          action: "start",
                          skill: selected,
                          level: next,
                        })
                      }
                    >
                      {g.tasks.some(
                        (t) => t.skill === selected && t.level === next,
                      )
                        ? "이미 시작한 과제예요"
                        : `LV${next} 과제 시작 · 완료 확인 후 ${rewards[next]}점`}
                    </button>
                  )}
                </>
              );
            })()}
          </section>
        </DetailDialog>
      )}
    </div>
  );
}
