"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { loginDestination, signInUrl } from "@/lib/login-destination";

export const demoLogin = {
  email: "demo@career.dev",
  password: "career-demo-2026",
};

const kakaoMessages: Record<string, string> = {
  kakao_state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
  kakao_cancelled: "카카오 로그인을 취소했습니다.",
  kakao_failed: "카카오 로그인에 실패했습니다. 다시 시도해 주세요.",
  kakao_config:
    "카카오 로그인 연결 설정을 확인해야 합니다. 관리자에게 문의해 주세요.",
  kakao_token:
    "카카오 로그인 인증을 완료하지 못했습니다. 카카오 로그인을 다시 눌러 주세요.",
  kakao_profile:
    "카카오 계정 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
  kakao_existing:
    "같은 이메일의 계정이 있습니다. 기존 이메일과 비밀번호로 로그인해 주세요.",
  kakao_email: "가입을 완료하려면 카카오 계정의 이메일 제공에 동의해 주세요.",
  kakao_registration_expired:
    "카카오 인증이 만료됐습니다. 카카오 로그인을 다시 진행해 주세요.",
};
export function SignInForm({
  initialError = "",
  initialRegistration,
  destination = "/analysis",
}: {
  initialError?: string;
  initialRegistration?: { email: string; name: string; setup: boolean };
  destination?: string;
} = {}) {
  const router = useRouter();
  const [email, setEmail] = useState(initialRegistration?.email || "");
  const [mode, setMode] = useState<"login" | "register">(
    initialRegistration ? "register" : "login",
  );
  const [name, setName] = useState(initialRegistration?.name || "");
  const [age, setAge] = useState("");
  const [school, setSchool] = useState("");
  const [major, setMajor] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
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
          ...(action === "register"
            ? {
                name,
                age: age === "" ? null : Number(age),
                school,
                major,
                confirmation,
                kakao: !!initialRegistration,
              }
            : {}),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || "계정 연결을 완료하지 못했어요.");
      window.dispatchEvent(new Event("career:account"));
      router.push(loginDestination(destination));
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "로그인하지 못했어요.");
      setBusy(false);
    }
  }
  return (
    <section className="career-panel sign-in-panel">
      <h1>
        {initialRegistration?.setup
          ? "비밀번호 설정"
          : mode === "login"
            ? "로그인"
            : "회원가입"}
      </h1>
      <p>
        {initialRegistration
          ? "카카오 계정 확인이 완료됐습니다. Career에서 사용할 비밀번호를 설정해 주세요."
          : mode === "register"
            ? "이메일 또는 카카오 계정으로 가입할 수 있습니다."
            : "로그인하면 GitHub와 이력서로 내 경험을 분석할 수 있어요."}
      </p>
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
              readOnly={!!initialRegistration?.setup}
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
            maxLength={200}
            readOnly={!!initialRegistration}
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
            minLength={mode === "register" ? 10 : 1}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === "register" && (
          <label>
            비밀번호 확인
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              maxLength={128}
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
        )}
        {mode === "register" && !initialRegistration?.setup && (
          <fieldset className="registration-optional">
            <legend>
              추가 정보 <span>선택</span>
            </legend>
            <label>
              나이 (선택)
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={120}
                step={1}
                value={age}
                onChange={(event) => setAge(event.target.value)}
              />
            </label>
            <label>
              학교 (선택)
              <input
                autoComplete="organization"
                maxLength={60}
                value={school}
                onChange={(event) => setSchool(event.target.value)}
              />
            </label>
            <label>
              학과 (선택)
              <input
                maxLength={60}
                value={major}
                onChange={(event) => setMajor(event.target.value)}
              />
            </label>
          </fieldset>
        )}
        {error && (
          <div role="alert" className="career-error">
            <p>{error}</p>
            {error === kakaoMessages.kakao_email && (
              <a
                href={
                  "/api/auth/kakao?" +
                  new URLSearchParams({
                    consent: "email",
                    next: loginDestination(destination),
                  })
                }
                className="kakao-consent-link"
              >
                이메일 제공 동의
              </a>
            )}
          </div>
        )}
        <button className="career-primary" disabled={busy}>
          {busy
            ? "연결 중…"
            : mode === "login"
              ? "로그인"
              : initialRegistration?.setup
                ? "비밀번호 설정 완료"
                : "가입하고 분석 시작하기"}
        </button>
      </form>
      {!initialRegistration && (
        <form
          action="/api/auth/kakao"
          method="get"
          className="kakao-login-form"
        >
          <input
            type="hidden"
            name="next"
            value={loginDestination(destination)}
          />
          <button
            type="submit"
            className="kakao-login-button"
            disabled={!kakaoReady || busy}
          >
            <Image
              src="/auth/kakao-login-ko.svg"
              alt="카카오 로그인"
              width={224}
              height={46}
              loading="eager"
              unoptimized
            />
          </button>
        </form>
      )}
      {!initialRegistration && !kakaoReady && (
        <p className="kakao-login-note">카카오 로그인 연결 준비 중</p>
      )}
      {mode === "login" && (
        <Link className="auth-secondary-link" href="/forgot-password">
          비밀번호 찾기
        </Link>
      )}
      <button
        className="header-login"
        disabled={busy}
        onClick={async () => {
          if (initialRegistration) {
            await fetch("/api/auth/kakao/registration", { method: "DELETE" });
            router.replace(signInUrl(destination));
            router.refresh();
            return;
          }
          setMode(mode === "login" ? "register" : "login");
          setError("");
        }}
      >
        {initialRegistration
          ? "가입 취소"
          : mode === "login"
            ? "회원가입"
            : "로그인으로 전환"}
      </button>
      {!initialRegistration && (
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
      )}
    </section>
  );
}
