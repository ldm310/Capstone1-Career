"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";

export function PasswordRecoveryForm({ reset = false }: { reset?: boolean }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [token, setToken] = useState("");
  const capturedToken = useRef<string | null>(null);
  const [ready, setReady] = useState(!reset);
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!reset) return;
    capturedToken.current ??=
      new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    const value = capturedToken.current;
    window.history.replaceState(null, "", window.location.pathname);
    void Promise.resolve().then(() => {
      setToken(value);
      setReady(true);
      if (!/^[a-f0-9]{64}$/.test(value))
        setError("재설정 링크가 올바르지 않습니다. 새 링크를 요청해 주세요.");
    });
  }, [reset]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (reset && password !== confirmation) {
      setError("비밀번호 확인이 일치하지 않습니다.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        reset ? "/api/account/password-reset" : "/api/account/recovery",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            reset ? { token, password, confirmation } : { email },
          ),
        },
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || "요청을 처리하지 못했습니다.");
      setComplete(true);
      setPassword("");
      setConfirmation("");
      setToken("");
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "요청을 처리하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel recovery-panel">
      <h1>
        {complete && reset
          ? "비밀번호 변경 완료"
          : reset
            ? "새 비밀번호 설정"
            : "비밀번호 찾기"}
      </h1>
      {complete ? (
        <div className="auth-success" role="status">
          <p>
            {reset
              ? "비밀번호가 변경됐습니다. 모든 기기에서 다시 로그인해 주세요."
              : "가입된 이메일이라면 비밀번호 재설정 링크를 보냈습니다. 메일함을 확인해 주세요."}
          </p>
        </div>
      ) : (
        <>
          <p>
            {reset
              ? "새 비밀번호를 설정해 주세요."
              : "가입한 이메일로 비밀번호 재설정 링크를 보내드립니다."}
          </p>
          <form onSubmit={submit}>
            {reset ? (
              <>
                <label>
                  새 비밀번호
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={10}
                    maxLength={128}
                    required
                    value={password}
                    disabled={busy || !ready || !token}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </label>
                <label>
                  비밀번호 확인
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={10}
                    maxLength={128}
                    required
                    value={confirmation}
                    disabled={busy || !ready || !token}
                    onChange={(event) => setConfirmation(event.target.value)}
                  />
                </label>
              </>
            ) : (
              <label>
                이메일
                <input
                  type="email"
                  autoComplete="email"
                  maxLength={200}
                  required
                  value={email}
                  disabled={busy}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
            )}
            {error && (
              <p className="career-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="career-primary"
              disabled={busy || !ready || (reset && !token)}
            >
              {busy
                ? "처리 중…"
                : reset
                  ? "비밀번호 변경"
                  : "재설정 링크 보내기"}
            </button>
          </form>
        </>
      )}
      <div className="auth-links">
        <Link href="/sign-in">로그인</Link>
        {reset && <Link href="/forgot-password">재설정 링크 다시 요청</Link>}
      </div>
    </section>
  );
}
