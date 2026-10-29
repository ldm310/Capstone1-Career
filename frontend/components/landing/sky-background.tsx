"use client";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
const photos = [
  "/images/career-sky.jpg",
  "/images/career-clouds-2.jpg",
  "/images/career-clouds-3.jpg",
];
const SkyContext = createContext({ index: 0, paused: false, toggle: () => {} });
export function SkyBackgroundProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const ready = useRef(new Set([0]));
  useEffect(() => {
    const images = photos.slice(1).map((src, i) => {
      const image = new Image();
      image.onload = () => ready.current.add(i + 1);
      image.src = src;
      return image;
    });
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const preference = () => setPaused(media.matches);
    preference();
    media.addEventListener("change", preference);
    return () => {
      images.forEach((image) => {
        image.onload = null;
      });
      media.removeEventListener("change", preference);
    };
  }, []);
  useEffect(() => {
    if (paused) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const schedule = () => {
      clearInterval(timer);
      if (document.hidden) return;
      timer = setInterval(
        () =>
          setIndex((current) => {
            for (let step = 1; step < photos.length; step++) {
              const next = (current + step) % photos.length;
              if (ready.current.has(next)) return next;
            }
            return current;
          }),
        5000,
      );
    };
    schedule();
    document.addEventListener("visibilitychange", schedule);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, [paused]);
  return (
    <SkyContext.Provider
      value={{ index, paused, toggle: () => setPaused((value) => !value) }}
    >
      {children}
    </SkyContext.Provider>
  );
}
export function SkyBackground({ className }: { className: string }) {
  const { index, paused } = useContext(SkyContext);
  return (
    <div
      className={`${className} cloud-slideshow`}
      data-cloud-index={index}
      data-paused={paused}
      aria-hidden="true"
    >
      {photos.map((src, i) => (
        <div
          key={src}
          className={`cloud-slide cloud-slide-${i} ${i === index ? "is-active" : ""}`}
          style={{ backgroundImage: `url("${src}")` }}
        />
      ))}
    </div>
  );
}
export function SkyPlayback() {
  const { paused, toggle } = useContext(SkyContext);
  return (
    <button
      className="sky-playback"
      onClick={toggle}
      aria-label={
        paused ? "구름 배경 자동 전환 재생" : "구름 배경 자동 전환 일시정지"
      }
    >
      {paused ? <Play size={13} /> : <Pause size={13} />}
      <span>배경 {paused ? "재생" : "멈춤"}</span>
    </button>
  );
}
