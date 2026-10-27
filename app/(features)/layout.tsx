import { Suspense } from "react";
import { FeatureShell } from "@/components/layout/feature-shell";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../studies.css";
import "../skills.css";
import "../readability.css";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <FeatureShell>{children}</FeatureShell>
    </Suspense>
  );
}
