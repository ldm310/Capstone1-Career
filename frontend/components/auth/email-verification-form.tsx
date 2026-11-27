"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
export function EmailVerificationForm() {
  const captured = useRef<string | null>(null);
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    captured.current ??=
      new URLSearchParams(location.hash.slice(1)).get("token") || "";
    history.replaceState(null, "", location.pathname);
    void Promise.resolve().then(() => {
      setToken(captured.current!);
      setReady(true);
    });
  }, []);
  async function submit() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/account/email-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          token ? { action: "confirm", token } : { action: "request" },
        ),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setComplete(true);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "요청을 처리하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel">
      <h1>이메일 인증</h1>
      <p>
        로그인, 회원가입과 별도로 이메일 소유 여부를 확인합니다. 인증하지 않아도
        기존 기능은 사용할 수 있습니다.
      </p>
      {complete ? (
        <div className="auth-success" role="status">
          {token
            ? "이메일 인증이 완료됐습니다."
            : "인증 메일을 보냈습니다. 메일함을 확인해 주세요."}
        </div>
      ) : (
        <>
          <button
            className="career-primary"
            disabled={!ready || busy}
            onClick={() => void submit()}
          >
            {busy
              ? "처리 중…"
              : token
                ? "이메일 인증 완료"
                : "인증 메일 보내기"}
          </button>
          {error && (
            <p className="career-error" role="alert">
              {error}
            </p>
          )}
        </>
      )}
      <div className="auth-links">
        <Link href="/sign-in">로그인</Link>
        <Link href="/">홈</Link>
      </div>
    </section>
  );
}
