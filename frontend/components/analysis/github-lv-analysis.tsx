"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { signInUrl } from "@/lib/login-destination";
import type {
  LvCategoryCode,
  LvJob,
  LvJobStatus,
  LvProfile,
} from "@/types/lv-stat";

// GitHub 계정 하나를 분석해 달라고 요청하고(POST /api/lv-stat/analysis), 진행과 결과 요약을 보여 준다.
// 공고마다의 LV는 공고 상세의 레이더 차트가 이 결과로 그린다. 로그인 여부는 GET의 401로 안다.
// 스테이징 스위치가 꺼진 서버(운영)는 GET이 404라 칸을 그리지 않는다. 첫 GET이 답하기 전에도 그리지 않는다
// (운영에서 칸이 잠깐 보였다 사라지지 않게).

const route = "/api/lv-stat/analysis";
// 요청이 대기·진행 중일 때만 이 간격으로 다시 읽는다.
const pollMs = 5000;
// 「Claude 임시값」 요청이 done인데 받은 결과가 그 요청의 것(profile.jobId가 같음)이 아니면 같은 간격으로 이만큼 더 읽는다.
// 작업자는 결과를 먼저 쓰므로 곧 온다. 그래도 안 오면 읽기를 멈추고 resultLost를 보인다.
const extraReads = 3;
const resultLost = "분석 결과를 불러오지 못했어요.";
// 요약에 보이는 카테고리 순서(lv-stat 카테고리 7개).
const order: LvCategoryCode[] = ["L", "O", "B", "E", "D", "F", "A"];
// 서버가 오류 글을 주지 않았거나 연결이 끊겼을 때(기존 분석 흐름과 같은 글).
const offline = "연결을 확인해 주세요.";

interface State {
  // null: 아직 모름(첫 GET 전, 칸을 그리지 않음). false: GET·POST가 401로 답함.
  signedIn: boolean | null;
  // GET이 404로 답함: 스테이징 스위치가 꺼진 서버라 칸을 그리지 않고 다시 읽지 않는다.
  off: boolean;
  loginNote: string;
  job: LvJob | null;
  profile: LvProfile | null;
  // GET이 401·200이 아닌 답을 줬을 때의 글. 다음 GET이 200이면 지운다.
  readError: string;
  // 끝난 GET 수. 진행 중이면 GET이 끝날 때마다 다음 읽기를 잡는다.
  reads: number;
  // done인 요청과 그 요청의 것이 아닌 결과를 연달아 받은 횟수(그런 답이 아니면 0). 0보다 크면 결과를 보이지 않는다.
  stale: number;
}

type Reply = { status: number; body: unknown };

async function call(init?: RequestInit): Promise<Reply> {
  const response = await fetch(route, { cache: "no-store", ...init });
  return {
    status: response.status,
    body: await response.json().catch(() => null),
  };
}

function errorText(body: unknown) {
  const error = (body as { error?: unknown } | null)?.error;
  return typeof error === "string" && error ? error : offline;
}

const active = (status: LvJobStatus | undefined) =>
  status === "queued" || status === "running";

// GET 한 번의 답을 화면 상태에 넣는다. reply가 null이면 연결이 끊긴 것이다: 진행 중이면 다음 차례에 다시 읽고,
// 첫 읽기였으면 입력 칸을 연다(로그인이 안 됐으면 POST가 401로 알려 준다).
function received(state: State, reply: Reply | null): State {
  const reads = state.reads + 1;
  if (!reply) return { ...state, reads, signedIn: state.signedIn ?? true };
  if (reply.status === 404)
    return { ...state, reads, off: true, job: null, profile: null };
  if (reply.status === 401)
    return {
      ...state,
      reads,
      signedIn: false,
      loginNote: errorText(reply.body),
      job: null,
      profile: null,
    };
  if (reply.status !== 200)
    return {
      ...state,
      reads,
      signedIn: true,
      readError: errorText(reply.body),
    };
  const body = reply.body as { job: LvJob | null; profile: LvProfile | null };
  const stale =
    body.job?.status === "done" && body.profile?.jobId !== body.job.id;
  return {
    ...state,
    reads,
    signedIn: true,
    readError: "",
    job: body.job,
    profile: body.profile,
    stale: stale ? state.stale + 1 : 0,
  };
}

function progressText(job: LvJob) {
  const stage = job.stage ?? "대기";
  return job.progress
    ? `${stage} (${job.progress.done}/${job.progress.total})`
    : stage;
}

export function GithubLvAnalysis() {
  const titleId = useId();
  const [state, setState] = useState<State>({
    signedIn: null,
    off: false,
    loginNote: "",
    job: null,
    profile: null,
    readError: "",
    reads: 0,
    stale: 0,
  });
  const [url, setUrl] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  // 같은 순간의 두 번 누름이 요청 두 개가 되지 않게(state는 다음 그리기에야 바뀐다).
  const lock = useRef(false);
  const running = active(state.job?.status);
  // done인데 그 요청의 결과를 아직 받지 못함: extraReads번까지 더 읽는다.
  const settling = state.stale > 0 && state.stale <= extraReads;

  // 처음 한 번 바로 읽고, 그 뒤로는 대기·진행 중이거나 결과를 기다릴 때만 5초마다 읽는다. 끝·실패면 멈추고, 화면을
  // 떠나면 잡아 둔 읽기와 보낸 요청을 모두 거둔다.
  useEffect(() => {
    if (state.reads > 0 && !running && !settling) return;
    const controller = new AbortController();
    const timer = setTimeout(
      () => {
        call({ signal: controller.signal }).then(
          (reply) => {
            if (!controller.signal.aborted)
              setState((current) => received(current, reply));
          },
          () => {
            if (!controller.signal.aborted)
              setState((current) => received(current, null));
          },
        );
      },
      state.reads > 0 ? pollMs : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [state.reads, running, settling]);

  async function send(address: string) {
    if (lock.current) return;
    lock.current = true;
    setSending(true);
    setSendError("");
    try {
      const reply = await call({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: address }),
      });
      const job = (reply.body as { job?: LvJob } | null)?.job;
      if (reply.status === 202 && job)
        setState((current) => ({ ...current, job, stale: 0 }));
      else if (reply.status === 401)
        setState((current) => ({
          ...current,
          signedIn: false,
          loginNote: errorText(reply.body),
          job: null,
          profile: null,
          stale: 0,
        }));
      else setSendError(errorText(reply.body));
    } catch {
      setSendError(offline);
    } finally {
      lock.current = false;
      setSending(false);
    }
  }

  if (state.off || state.signedIn === null) return null;
  const { job, profile } = state;
  const failed = job?.status === "failed";
  const problem =
    sendError ||
    state.readError ||
    (state.stale > extraReads ? resultLost : "");
  return (
    <section className="github-lv-analysis" aria-labelledby={titleId}>
      <h2 id={titleId}>GitHub 계정으로 공고별 LV 보기</h2>
      <p className="github-lv-guide">
        분석이 끝나면 공고 상세의 레이더 차트에 공고마다 LV가 나와요.
      </p>
      {state.signedIn === false ? (
        <p className="github-lv-login">
          {state.loginNote}{" "}
          <Link href={signInUrl("/analysis")}>로그인, 회원가입</Link>
        </p>
      ) : (
        <form
          className="github-lv-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void send(url.trim());
          }}
        >
          <input
            type="url"
            autoComplete="url"
            aria-labelledby={titleId}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://github.com/아이디"
            disabled={sending || running}
          />
          <button type="submit" disabled={!url.trim() || sending || running}>
            분석 시작
          </button>
        </form>
      )}
      {problem && (
        <p className="github-lv-error" role="alert">
          {problem}
        </p>
      )}
      <p className="github-lv-progress" role="status">
        {job && running ? progressText(job) : ""}
      </p>
      {failed && (
        <div className="github-lv-failure">
          <p className="github-lv-error" role="alert">
            {job.error ?? "실패"}
          </p>
          <button
            type="button"
            disabled={sending}
            onClick={() => void send(job.input)}
          >
            다시 시도
          </button>
        </div>
      )}
      {profile && !state.stale && (
        <div className="github-lv-summary">
          <ul>
            {order.map((code) => {
              const category = profile.categories[code];
              return (
                <li key={code}>
                  <span>{category.name}</span>{" "}
                  <strong>
                    {category.lv === null
                      ? "판정 불가"
                      : `LV ${category.lv.toFixed(1)}`}
                  </strong>
                  {category.unknown > 0 && (
                    <small> · 모름 {category.unknown}개</small>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="github-lv-labels">{profile.labels.join(" · ")}</p>
        </div>
      )}
    </section>
  );
}
