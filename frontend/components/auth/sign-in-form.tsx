"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export const demoLogin = {
  email: "demo@career.dev",
  password: "career-demo-2026",
};

const kakaoMessages: Record<string, string> = {
  kakao_state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
  kakao_cancelled: "카카오 로그인을 취소했습니다.",
  kakao_failed: "카카오 로그인에 실패했습니다. 다시 시도해 주세요.",
  kakao_existing:
    "같은 이메일의 계정이 있습니다. 기존 이메일과 비밀번호로 로그인해 주세요.",
  kakao_email: "카카오 계정의 이메일 제공 동의가 필요합니다.",
};
export function SignInForm({
  initialError = "",
}: { initialError?: string } = {}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(kakaoMessages[initialError] || "");
  const [kakaoReady, setKakaoReady] = useState(false);
  useEffect(() => {
    void fetch("/api/auth/kakao/status")
      .then((response) => response.json())
      .then((data) => setKakaoReady(data.configured === true))
      .catch(() => {});
  }, []);
  async function login(
    next = { email, password },
    action: "login" | "register" = mode,
  ) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/account", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          ...next,
          ...(action === "register" ? { name } : {}),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || "계정 연결을 완료하지 못했어요.");
      router.push("/analysis");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "로그인하지 못했어요.");
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel">
      <h1>{mode === "login" ? "로그인" : "회원가입"}</h1>
      <p>로그인하면 GitHub와 이력서로 내 경험을 분석할 수 있어요.</p>
      <form action="/api/auth/kakao" method="get">
        <button
          type="submit"
          className="kakao-login-button"
          disabled={!kakaoReady || busy}
        >
          카카오로 시작하기
        </button>
      </form>
      {!kakaoReady && (
        <p className="kakao-login-note">카카오 로그인 연결 준비 중</p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void login();
        }}
      >
        {mode === "register" && (
          <label>
            이름
            <input
              autoComplete="name"
              required
              maxLength={60}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
        )}
        <label>
          이메일
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            autoComplete={
              mode === "register" ? "new-password" : "current-password"
            }
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p role="alert" className="career-error">
            {error}
          </p>
        )}
        <button className="career-primary" disabled={busy}>
          {busy
            ? "연결 중…"
            : mode === "login"
              ? "로그인"
              : "가입하고 분석 시작하기"}
        </button>
      </form>
      <button
        className="header-login"
        disabled={busy}
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setError("");
        }}
      >
        {mode === "login" ? "회원가입" : "로그인으로 전환"}
      </button>
      <div className="sign-in-demo">
        <strong>데모 계정</strong>
        <p>
          {demoLogin.email}
          <br />
          {demoLogin.password}
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setEmail(demoLogin.email);
            setPassword(demoLogin.password);
            void login(demoLogin, "login");
          }}
        >
          데모 계정으로 로그인
        </button>
      </div>
    </section>
  );
}
