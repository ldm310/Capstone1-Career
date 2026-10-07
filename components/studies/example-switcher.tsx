"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { tierLabels, type StudyTier } from "@/lib/study-prototype";

export function ExampleSwitcher({ tier }: { tier: StudyTier }) {
  const pathname = usePathname();
  const params = useSearchParams();
  function href(next: StudyTier) {
    const search = new URLSearchParams(params.toString());
    search.set("demo", next);
    search.delete("room");
    return `${pathname}?${search}`;
  }
  return (
    <aside className="study-example-banner">
      <div>
        <strong>예시 데이터 체험</strong>
        <p>
          가상 공고와 예시 수준이에요. LV·상대 수준 기준은 미정이며 실제 판정이
          아니에요.
        </p>
      </div>
      <nav aria-label="예시 수준 선택">
        {(["low", "middle", "high"] as const).map((value) => (
          <Link
            key={value}
            href={href(value)}
            aria-current={tier === value ? "page" : undefined}
          >
            {tierLabels[value]}
          </Link>
        ))}
      </nav>
      <Link href="/jobs" className="study-example-exit">
        실제 공고로 돌아가기
      </Link>
    </aside>
  );
}
