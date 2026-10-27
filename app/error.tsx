"use client";
import { EmptyState } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="standalone">
      <EmptyState
        error
        title="불러오지 못했어요."
        description="잠시 후 다시 시도해 주세요."
        action={<Button onClick={reset}>다시 시도</Button>}
      />
    </main>
  );
}
