import { AnalysisFlow } from "@/components/analysis/analysis-flow";
import { GithubLvAnalysis } from "@/components/analysis/github-lv-analysis";
import "../../analysis.css";

export default function Page() {
  return (
    <>
      <GithubLvAnalysis />
      <AnalysisFlow />
    </>
  );
}
