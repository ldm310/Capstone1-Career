import { Suspense } from "react";
import { AppShell } from "@/components/layout/app-shell";
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Suspense fallback={<p role="status">화면을 준비하고 있어요…</p>}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
