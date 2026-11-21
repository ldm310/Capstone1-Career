"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export const demoLogin = {
  email: "demo@career.dev",
  password: "career-demo-2026",
};

export function SignInForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
        {mode === "login"
          ? "처음이신가요? 회원가입"
          : "이미 계정이 있나요? 로그인"}
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
