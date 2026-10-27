export interface Finding {
  id: string;
  skill: string;
  type: "implementation" | "learning" | "career";
  title: string;
  quote: string;
  url: string;
  detectedAt: string;
}
export interface AnalysisRun {
  id: string;
  title: string;
  at: string;
  findings: Finding[];
}
export interface JobAnalysis {
  id: string;
  company: string;
  title: string;
  url: string;
  required: string[];
  preferred: string[];
  unknown: string[];
  text: string;
}
export interface CareerTask {
  id: string;
  title: string;
  date: string;
  done: boolean;
}
export interface CareerDocument {
  id: string;
  name: string;
  at: string;
}
export interface Workspace {
  role: string;
  region: string;
  experience: string;
  hours: number;
  targetDate: string;
  runs: AnalysisRun[];
  job: JobAnalysis | null;
  tasks: CareerTask[];
  documents: CareerDocument[];
  answers: Record<string, string>;
  savedJobs: import("./public-job").PublicJob[];
}
export const emptyWorkspace: Workspace = {
  role: "data",
  region: "",
  experience: "",
  hours: 5,
  targetDate: "",
  runs: [],
  job: null,
  tasks: [],
  documents: [],
  answers: {},
  savedJobs: [],
};
