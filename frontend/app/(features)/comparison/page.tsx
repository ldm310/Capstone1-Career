import { user, isGuest } from "@/lib/server/store";
import { AnalysisFlow } from "@/components/analysis/analysis-flow";
import { ComparisonTutorial } from "@/components/jobs/comparison-tutorial";
import "../../analysis.css";
import "./tutorial.css";

export default async function Page() {
  const current = await user();
  return current && !isGuest(current.id) ? (
    <AnalysisFlow />
  ) : (
    <ComparisonTutorial />
  );
}
