"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import {
  careerOptions,
  educationOptions,
  emptyProfile,
  type Profile,
} from "@/types/profile";

interface Account {
  name: string;
  email: string;
  profile: Profile;
  demo: boolean;
}
async function post(body: object) {
  const r = await fetch("/api/account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || "저장하지 못했어요.");
  return d;
}
// zod 오류는 JSON 배열 문자열로 오므로 첫 메시지만 보여준다.
function readable(e: unknown) {
  const text = e instanceof Error ? e.message : "저장하지 못했어요.";
  try {
    const issues = JSON.parse(text);
    if (Array.isArray(issues) && issues[0]?.message) return issues[0].message;
  } catch {}
  return text;
}

// 마이페이지 내 정보: 기본 정보, 학력과 경력, 희망 조건을 고치고 비밀번호를 바꾼다.
export function ProfilePanel() {
  const [account, setAccount] = useState<Account | null | undefined>();
  const [status, setStatus] = useState({ text: "", error: false });
  const [passwordStatus, setPasswordStatus] = useState({
    text: "",
    error: false,
  });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // 늦게 온 응답이 입력 중인 값을 덮어쓰지 않게 한 번만 반영한다.
    let active = true;
    fetch("/api/account")
      .then((r) => r.json())
      .then((d) => {
        if (!active) return;
        setAccount(
          d.user && !d.guest
            ? {
                name: d.user.name,
                email: d.user.email,
                profile: { ...emptyProfile, ...d.profile },
                demo: !!d.demo,
              }
            : null,
        );
      })
      .catch(() => {
        if (active) setAccount(null);
      });
    return () => {
      active = false;
    };
  }, []);
  if (account === undefined) return <LoadingSpinner inline />;
  if (!account)
    return (
      <div className="mypage-empty">
        <p>로그인하면 내 정보를 수정할 수 있어요.</p>
        <Link className="cta" href="/sign-in">
          로그인 <ArrowRight size={16} />
        </Link>
      </div>
    );
  const set = (patch: Partial<Account>) => setAccount({ ...account, ...patch });
  const setProfile = (patch: Partial<Profile>) =>
    set({ profile: { ...account.profile, ...patch } });
  const p = account.profile;
  const field = (
    key: keyof Profile,
    label: string,
    placeholder: string,
    type = "text",
  ) => (
    <label>
      {label}
      <input
        type={type}
        value={p[key]}
        placeholder={placeholder}
        maxLength={key === "github" ? 200 : 60}
        onChange={(e) => setProfile({ [key]: e.target.value })}
      />
    </label>
  );
  return (
    <div className="mypage-profile">
      <section className="mypage-card mypage-summary" aria-label="내 정보 요약">
        <span className="mypage-avatar" aria-hidden="true">
          {account.name.slice(0, 1)}
        </span>
        <div>
          <strong>{account.name}</strong>
          <span>{account.email}</span>
          {p.intro && <p>{p.intro}</p>}
        </div>
        <dl>
          <div>
            <dt>학력</dt>
            <dd>{p.education || "-"}</dd>
          </div>
          <div>
            <dt>경력</dt>
            <dd>{p.career || "-"}</dd>
          </div>
          <div>
            <dt>희망 근무지</dt>
            <dd>{p.location || "-"}</dd>
          </div>
        </dl>
      </section>
      <form
        className="mypage-card mypage-form"
        aria-labelledby="profile-form-title"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const d = await post({
              action: "update",
              name: account.name,
              email: account.email,
              profile: account.profile,
            });
            set({ name: d.user.name, email: d.user.email });
            window.dispatchEvent(new Event("career:account"));
            setStatus({ text: "저장했어요.", error: false });
          } catch (err) {
            setStatus({ text: readable(err), error: true });
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2 id="profile-form-title">내 정보 수정</h2>
        <fieldset>
          <legend>기본 정보</legend>
          <label>
            이름
            <input
              required
              maxLength={60}
              value={account.name}
              onChange={(e) => set({ name: e.target.value })}
            />
          </label>
          <label>
            이메일
            <input
              type="email"
              required
              maxLength={200}
              value={account.email}
              disabled={account.demo}
              onChange={(e) => set({ email: e.target.value })}
            />
          </label>
        </fieldset>
        <fieldset>
          <legend>학력, 경력</legend>
          <label>
            최종 학력
            <select
              value={p.education}
              onChange={(e) => setProfile({ education: e.target.value })}
            >
              <option value="">선택 안 함</option>
              {educationOptions.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </label>
          <label>
            경력
            <select
              value={p.career}
              onChange={(e) => setProfile({ career: e.target.value })}
            >
              <option value="">선택 안 함</option>
              {careerOptions.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </label>
          {field("school", "학교", "예: 한국대학교")}
          {field("major", "전공", "예: 컴퓨터공학과")}
        </fieldset>
        <fieldset>
          <legend>희망 조건, 링크</legend>
          {field("location", "희망 근무지", "예: 서울, 경기")}
          {field("github", "GitHub", "https://github.com/아이디", "url")}
          <label className="mypage-wide">
            한 줄 소개
            <textarea
              rows={2}
              maxLength={200}
              value={p.intro}
              placeholder="관심 있는 분야나 강점을 짧게 적어 주세요."
              onChange={(e) => setProfile({ intro: e.target.value })}
            />
          </label>
        </fieldset>
        <div className="mypage-actions">
          <p
            role="status"
            className={status.error ? "mypage-error" : "mypage-ok"}
          >
            {status.text}
          </p>
          <button className="career-primary" disabled={busy}>
            저장
          </button>
        </div>
      </form>
      <form
        className="mypage-card mypage-form"
        aria-labelledby="password-form-title"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const f = new FormData(form);
          if (f.get("next") !== f.get("confirm"))
            return setPasswordStatus({
              text: "새 비밀번호가 서로 달라요.",
              error: true,
            });
          try {
            await post({
              action: "password",
              current: f.get("current"),
              next: f.get("next"),
            });
            form.reset();
            setPasswordStatus({ text: "비밀번호를 바꿨어요.", error: false });
          } catch (err) {
            setPasswordStatus({ text: readable(err), error: true });
          }
        }}
      >
        <h2 id="password-form-title">비밀번호 변경</h2>
        {account.demo && (
          <p className="mypage-note">
            데모 계정은 이메일과 비밀번호를 바꿀 수 없어요.
          </p>
        )}
        <fieldset disabled={account.demo}>
          <legend className="sr-only">비밀번호</legend>
          <label>
            현재 비밀번호
            <input
              name="current"
              type="password"
              required
              autoComplete="current-password"
            />
          </label>
          <label>
            새 비밀번호
            <input
              name="next"
              type="password"
              required
              minLength={10}
              maxLength={128}
              autoComplete="new-password"
              placeholder="10자 이상"
            />
          </label>
          <label>
            새 비밀번호 확인
            <input
              name="confirm"
              type="password"
              required
              minLength={10}
              maxLength={128}
              autoComplete="new-password"
            />
          </label>
        </fieldset>
        <div className="mypage-actions">
          <p
            role="status"
            className={passwordStatus.error ? "mypage-error" : "mypage-ok"}
          >
            {passwordStatus.text}
          </p>
          <button className="career-primary" disabled={account.demo}>
            변경
          </button>
        </div>
      </form>
    </div>
  );
}
