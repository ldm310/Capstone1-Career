"use client";
import { useEffect, useRef, useState } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  useReducedMotion,
} from "motion/react";
import { ArrowDown, ArrowRight, RotateCcw } from "lucide-react";
import {
  SkyBackground,
  SkyBackgroundProvider,
  SkyPlayback,
} from "./sky-background";
const key = "career:sky-intro:seen";
export function SkyExperience({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<"intro" | "leaving" | "open">("intro");
  const reduced = useReducedMotion();
  const enterRef = useRef<HTMLButtonElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const focusAfterEntry = useRef(false);
  const x = useMotionValue(0),
    y = useMotionValue(0);
  const rotateX = useSpring(x, { stiffness: 65, damping: 22 });
  const rotateY = useSpring(y, { stiffness: 65, damping: 22 });
  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (!active) return;
      let seen = !!window.location.hash;
      try {
        seen ||= sessionStorage.getItem(key) === "yes";
      } catch {
        /* Intro remains usable without storage. */
      }
      if (seen) setPhase("open");
      else enterRef.current?.focus();
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (phase === "open") return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [phase]);
  useEffect(() => {
    if (phase === "open" && focusAfterEntry.current) {
      contentRef.current
        ?.querySelector<HTMLElement>("h1")
        ?.focus({ preventScroll: true });
      focusAfterEntry.current = false;
    }
    if (phase === "intro") enterRef.current?.focus();
  }, [phase]);
  useEffect(() => {
    if (phase !== "leaving") return;
    const timer = setTimeout(
      () => {
        setPhase("open");
      },
      reduced ? 30 : 850,
    );
    return () => clearTimeout(timer);
  }, [phase, reduced]);
  function enter() {
    if (phase !== "intro") return;
    focusAfterEntry.current = true;
    try {
      sessionStorage.setItem(key, "yes");
    } catch {
      /* No persistence is required to enter. */
    }
    setPhase("leaving");
  }
  return (
    <SkyBackgroundProvider>
      <div className={`sky-experience sky-phase-${phase}`}>
        <div
          ref={contentRef}
          className="sky-home"
          inert={phase !== "open"}
          aria-hidden={phase !== "open"}
        >
          {children}
        </div>
        {phase !== "open" && (
          <div
            className="sky-intro"
            role="dialog"
            aria-modal="true"
            aria-label="Career 시작 화면"
            onKeyDown={(e) => {
              if (e.key === "Escape") enter();
              if (e.key === "Tab") {
                const buttons = Array.from(
                  e.currentTarget.querySelectorAll<HTMLButtonElement>("button"),
                );
                const current = buttons.indexOf(
                  document.activeElement as HTMLButtonElement,
                );
                e.preventDefault();
                buttons[
                  (current + (e.shiftKey ? -1 : 1) + buttons.length) %
                    buttons.length
                ]?.focus();
              }
            }}
          >
            <SkyBackground className="intro-sky-photo" />
            <SkyPlayback />
            <div className="intro-atmosphere" aria-hidden="true" />
            <div
              className="intro-scene"
              onPointerMove={(e) => {
                if (reduced || e.pointerType !== "mouse") return;
                const bounds = e.currentTarget.getBoundingClientRect();
                x.set(
                  (-(e.clientY - bounds.top - bounds.height / 2) /
                    bounds.height) *
                    8,
                );
                y.set(
                  ((e.clientX - bounds.left - bounds.width / 2) /
                    bounds.width) *
                    12,
                );
              }}
              onPointerLeave={() => {
                x.set(0);
                y.set(0);
              }}
            >
              <span className="intro-kicker">YOUR NEXT CHAPTER</span>
              <motion.span
                className="intro-title-group"
                style={{ rotateX, rotateY, transformPerspective: 1200 }}
              >
                <span className="intro-word">Career</span>
                <span className="intro-subtitle">
                  쌓아온 경험이,
                  <br className="intro-mobile-break" /> 더 넓은 가능성으로.
                </span>
                <span className="intro-description">
                  나의 기록에서 발견하는 다음 커리어
                </span>
              </motion.span>
              <button
                ref={enterRef}
                className="intro-click"
                aria-label="Career 홈페이지 열기"
                onClick={enter}
              >
                <span className="intro-click-link">
                  나의 Career 만나보기
                  <ArrowRight size={22} strokeWidth={1.6} aria-hidden="true" />
                </span>
                <span className="intro-keyboard">
                  Enter 키로도 시작할 수 있어요
                </span>
              </button>
              <span className="intro-bottom">
                EXPERIENCE BECOMES POSSIBILITY <ArrowDown size={13} />
              </span>
            </div>
          </div>
        )}
        {phase === "open" && (
          <button
            className="intro-replay"
            onClick={() => {
              window.scrollTo({ top: 0, behavior: "instant" });
              setPhase("intro");
              x.set(0);
              y.set(0);
              requestAnimationFrame(() => enterRef.current?.focus());
            }}
          >
            <RotateCcw size={13} />
            인트로 다시 보기
          </button>
        )}
      </div>
    </SkyBackgroundProvider>
  );
}
