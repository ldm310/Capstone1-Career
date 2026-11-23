"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
export function AdminSetup() {
  const router = useRouter();
  const token = useRef("");
  const [password, setPassword] = useState(""),
    [confirm, setConfirm] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const incoming = new URLSearchParams(window.location.hash.slice(1)).get(
      "token",
    );
    if (incoming) token.current = incoming;
    window.history.replaceState(null, "", window.location.pathname);
  }, []);
  async function activate() {
    setError("");
    if (password !== confirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/admin/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: token.current, password }),
        }),
        data = await response.json();
      if (!response.ok) throw new Error(data.error);
      router.replace("/notices");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "설정하지 못했습니다.");
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel">
      <h1>관리자 비밀번호 설정</h1>
      <p>설정 후 공지사항을 작성할 수 있습니다.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void activate();
        }}
      >
        <label>
          비밀번호
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label>
          비밀번호 확인
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            maxLength={128}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button className="career-primary" disabled={busy}>
          {busy ? "설정 중" : "설정하고 로그인"}
        </button>
      </form>
    </section>
  );
}
