"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BookOpen,
  CalendarDays,
  Check,
  ExternalLink,
  MessageCircle,
  Plus,
  Route,
  Send,
  Users,
} from "lucide-react";
import { tierLabels, type StudyOffer } from "@/lib/study-prototype";
import { useStudies, type StudyRoom as Room } from "./study-provider";

export function StudyRoom({
  room,
  offer,
  company,
  jobTitle,
}: {
  room: Room;
  offer: StudyOffer;
  company: string;
  jobTitle: string;
}) {
  const { update } = useStudies();
  const [tab, setTab] = useState("roadmap");
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  const completed = room.completed.filter(
    (i) => i < offer.roadmap.length,
  ).length;
  const progress = Math.round((completed / offer.roadmap.length) * 100);
  const tabs = [
    { key: "roadmap", label: "공동 로드맵", Icon: Route },
    { key: "members", label: "멤버", Icon: Users },
    { key: "chat", label: "채팅", Icon: MessageCircle },
    { key: "calendar", label: "일정", Icon: CalendarDays },
    { key: "resources", label: "자료 공유", Icon: BookOpen },
  ];
  const edit = (fn: (value: Room) => Room) => update(room.id, room.tier, fn);
  return (
    <div className="study-room">
      <Link className="study-back" href={`/studies?demo=${room.tier}`}>
        <ArrowLeft size={16} />내 스터디 목록
      </Link>
      <header className="study-room-heading">
        <div>
          <span className={`study-tier ${room.tier}`}>
            {tierLabels[room.tier]} 전용 · 예시
          </span>
          <h2>{offer.title}</h2>
          <p>
            {company} · {jobTitle}
          </p>
        </div>
        <Link href={`/jobs?job=${room.jobId}&demo=${room.tier}&view=study`}>
          연결된 공고 보기 <ExternalLink size={15} />
        </Link>
      </header>
      <div className="study-room-summary">
        <div>
          <Users size={21} />
          <span>
            참여 멤버<strong>나 1명</strong>
          </span>
        </div>
        <div>
          <Route size={21} />
          <span>
            목표
            <strong>
              {room.tier === "low"
                ? "Middle 준비"
                : room.tier === "middle"
                  ? "High 준비"
                  : "맞춤 심화 학습"}
            </strong>
          </span>
        </div>
        <div>
          <Check size={21} />
          <span>
            과제 진행
            <strong>
              {completed} / {offer.roadmap.length}개
            </strong>
          </span>
        </div>
      </div>
      <div className="study-progress-label">
        <span>나의 과제 진행률</span>
        <strong>{progress}%</strong>
      </div>
      <progress
        className="study-progress"
        max={100}
        value={progress}
        aria-label="나의 과제 진행률"
      />
      <p className="study-muted">
        혼자서도 바로 시작할 수 있어요. 현재는 예시 자료에 맞춘 로드맵이며,
        체크는 진행 기록으로만 남아요. 수준 판정·포인트는 바뀌지 않아요.
      </p>
      <nav className="study-room-tabs" aria-label="스터디 공간 메뉴">
        {tabs.map(({ key, label, Icon }) => (
          <button
            key={key}
            aria-pressed={tab === key}
            onClick={() => {
              setTab(key);
              setNotice("");
            }}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>
      <section
        className="study-room-panel"
        aria-label={tabs.find((t) => t.key === tab)?.label}
      >
        {tab === "roadmap" && (
          <>
            <div className="study-section-heading">
              <div>
                <h3>오늘부터 한 단계씩 준비해요</h3>
                <p>
                  {room.tier === "high"
                    ? "심화 목표"
                    : `${tierLabels[room.tier]}에서 다음 단계`}
                  에 맞춘 프로젝트 수행 경로예요.
                </p>
              </div>
            </div>
            <ol className="study-roadmap">
              {offer.roadmap.map((task, index) => (
                <li
                  key={task.title}
                  className={room.completed.includes(index) ? "complete" : ""}
                >
                  <span className="study-step-number">
                    {room.completed.includes(index) ? (
                      <Check size={20} />
                    ) : (
                      String(index + 1).padStart(2, "0")
                    )}
                  </span>
                  <div>
                    <h4>{task.title}</h4>
                    <p>{task.outcome}</p>
                    <span className="study-muted">
                      남길 자료: 코드 변경 · 실행 결과 · 작업 설명
                    </span>
                  </div>
                  <label>
                    <input
                      type="checkbox"
                      checked={room.completed.includes(index)}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        edit((r) => ({
                          ...r,
                          completed: checked
                            ? [...new Set([...r.completed, index])]
                            : r.completed.filter((v) => v !== index),
                        }));
                      }}
                    />
                    {room.completed.includes(index) ? "진행 완료" : "완료 기록"}
                  </label>
                </li>
              ))}
            </ol>
            <div className="study-learning-materials">
              <h4>학습자료</h4>
              <p>
                아래 공식 문서에서 필요한 내용을 확인하고, 참고한 자료는 ‘자료
                공유’에 모아보세요.
              </p>
              <a
                href="https://docs.python.org/ko/3/tutorial/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Python 공식 자습서 <ExternalLink size={14} />
              </a>
              <a
                href="https://docs.docker.com/get-started/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Docker 시작 가이드 <ExternalLink size={14} />
              </a>
            </div>
          </>
        )}
        {tab === "members" && (
          <>
            <h3>함께 준비하는 멤버</h3>
            <div className="study-member">
              <span className="study-avatar">나</span>
              <div>
                <strong>나 · 예시 참여자</strong>
                <p>
                  {tierLabels[room.tier]} · {completed}/{offer.roadmap.length}개
                  진행
                </p>
              </div>
            </div>
            <p className="study-muted">
              혼자 참여해도 개인 로드맵을 진행할 수 있어요. 실제 멤버 연결과
              공동 진행률은 서버 연동 후 제공돼요.
            </p>
          </>
        )}
        {tab === "chat" && (
          <>
            <h3>스터디 채팅</h3>
            <p className="study-muted">
              전송한 메시지는 이 브라우저에만 기록돼요. 실제 상대에게 전달되지
              않아요.
            </p>
            <div className="study-messages" aria-live="polite">
              {!room.messages.length && (
                <div className="study-empty">
                  <MessageCircle size={26} />
                  <p>오늘의 목표나 궁금한 점을 남겨보세요.</p>
                </div>
              )}
              {room.messages.map((item) => (
                <div className="study-message" key={item.id}>
                  <span>
                    나 ·{" "}
                    {new Date(item.at).toLocaleTimeString("ko-KR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <p>{item.text}</p>
                </div>
              ))}
            </div>
            <form
              className="study-chat-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (!message.trim()) return;
                const item = {
                  id: crypto.randomUUID(),
                  text: message.trim(),
                  at: new Date().toISOString(),
                };
                edit((r) => ({ ...r, messages: [...r.messages, item] }));
                setMessage("");
              }}
            >
              <label className="sr-only" htmlFor="study-message">
                채팅 메시지
              </label>
              <textarea
                id="study-message"
                placeholder="메시지를 입력하세요"
                maxLength={2000}
                rows={2}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
              <button className="study-primary" disabled={!message.trim()}>
                <Send size={16} />
                전송 · 체험
              </button>
            </form>
          </>
        )}
        {tab === "calendar" && (
          <>
            <h3>스터디 일정</h3>
            <p className="study-muted">
              함께할 작업이나 개인 학습 시간을 기록해요. 일정은 이 브라우저에
              저장되며 알림은 발송되지 않아요.
            </p>
            <form
              className="study-inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const data = new FormData(form);
                const title = String(data.get("title") || "").trim();
                const at = String(data.get("at") || "");
                if (!title || !Number.isFinite(Date.parse(at))) return;
                const item = { id: crypto.randomUUID(), title, at };
                edit((r) => ({ ...r, events: [...r.events, item] }));
                form.reset();
                setNotice("일정을 추가했어요.");
              }}
            >
              <label>
                일정 이름
                <input
                  name="title"
                  required
                  maxLength={100}
                  placeholder="예: 평가 결과 함께 확인하기"
                />
              </label>
              <label>
                날짜와 시간
                <input name="at" type="datetime-local" required />
              </label>
              <button className="study-primary">
                <Plus size={16} />
                일정 추가
              </button>
            </form>
            {!room.events.length && (
              <p className="study-empty">아직 등록한 일정이 없어요.</p>
            )}
            <ul className="study-item-list">
              {[...room.events]
                .sort((a, b) => a.at.localeCompare(b.at))
                .map((item) => (
                  <li key={item.id}>
                    <CalendarDays size={20} />
                    <div>
                      <strong>{item.title}</strong>
                      <p>{new Date(item.at).toLocaleString("ko-KR")}</p>
                    </div>
                    <button
                      aria-label={`${item.title} 일정 삭제`}
                      onClick={() => {
                        edit((r) => ({
                          ...r,
                          events: r.events.filter((v) => v.id !== item.id),
                        }));
                        setNotice("일정을 삭제했어요.");
                      }}
                    >
                      삭제
                    </button>
                  </li>
                ))}
            </ul>
          </>
        )}
        {tab === "resources" && (
          <>
            <h3>함께 볼 자료</h3>
            <p className="study-muted">
              문서·저장소·실행 결과 링크를 모아두세요. 예시 공간의 자료는 다른
              사용자에게 공개되지 않아요.
            </p>
            <form
              className="study-inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const data = new FormData(form);
                const title = String(data.get("title") || "").trim();
                const url = String(data.get("url") || "").trim();
                if (!title) return;
                try {
                  if (!["https:", "http:"].includes(new URL(url).protocol))
                    throw new Error();
                } catch {
                  setNotice(
                    "http 또는 https로 시작하는 올바른 링크를 입력해 주세요.",
                  );
                  return;
                }
                const item = { id: crypto.randomUUID(), title, url };
                edit((r) => ({ ...r, resources: [...r.resources, item] }));
                form.reset();
                setNotice("자료를 추가했어요.");
              }}
            >
              <label>
                자료 제목
                <input
                  name="title"
                  required
                  maxLength={100}
                  placeholder="예: 프로젝트 실행 결과"
                />
              </label>
              <label>
                자료 링크
                <input
                  name="url"
                  type="url"
                  required
                  maxLength={2000}
                  placeholder="https://…"
                />
              </label>
              <button className="study-primary">
                <Plus size={16} />
                자료 추가
              </button>
            </form>
            {!room.resources.length && (
              <p className="study-empty">첫 번째 참고 자료를 추가해 보세요.</p>
            )}
            <ul className="study-item-list">
              {room.resources.map((item) => (
                <li key={item.id}>
                  <BookOpen size={20} />
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
                    {item.title}
                    <ExternalLink size={14} />
                  </a>
                  <button
                    aria-label={`${item.title} 자료 삭제`}
                    onClick={() => {
                      edit((r) => ({
                        ...r,
                        resources: r.resources.filter((v) => v.id !== item.id),
                      }));
                      setNotice("자료를 삭제했어요.");
                    }}
                  >
                    삭제
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="study-form-status" role="status">
          {notice}
        </p>
      </section>
    </div>
  );
}
