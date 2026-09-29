"use client";
import { useEffect, useRef, type ReactNode } from "react";
export function DetailDialog({
  children,
  onClose,
}: {
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    el?.showModal();
    return () => {
      el?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="growth-detail"
      aria-label="기술 근거와 단계별 과제"
      onCancel={onClose}
    >
      {children}
    </dialog>
  );
}
