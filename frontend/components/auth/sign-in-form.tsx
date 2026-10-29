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
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function login(next = { email, password }) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/account", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "login", ...next }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || "로그인하지 못했어요.");
      router.push("/my-skills");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "로그인하지 못했어요.");
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel">
      <h1>로그인</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void login();
        }}
      >
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
            autoComplete="current-password"
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
          {busy ? "로그인 중…" : "로그인"}
        </button>
      </form>
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
            void login(demoLogin);
          }}
        >
          데모 계정으로 로그인
        </button>
      </div>
    </section>
  );
}
