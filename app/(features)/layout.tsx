import { Suspense } from "react";
import { FeatureShell } from "@/components/layout/feature-shell";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../studies.css";
import { StudyProvider } from "@/components/studies/study-provider";
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<p role="status">화면을 준비하고 있어요…</p>}>
      <StudyProvider>
        <FeatureShell>{children}</FeatureShell>
      </StudyProvider>
    </Suspense>
  );
}
