export type RoleId = import("@/lib/roles").SupportedRole;
export type EvidenceType =
  "implementation" | "learning" | "career" | "certificate";
export type EvidenceSource = "github" | "notion" | "cv" | "certificate";
export interface Role {
  id: RoleId;
  title: string;
  short: string;
  description: string;
  skills: string[];
}
export interface Skill {
  id: string;
  name: string;
  category: string;
}
export interface Evidence {
  id: string;
  skillId: string;
  type: EvidenceType;
  source: EvidenceSource;
  title: string;
  description: string;
  sourceUrl: string | null;
  detectedAt: string;
  details: string[];
}
export interface PersonalSkill {
  skillId: string;
  evidenceIds: string[];
}
export interface MarketSkill {
  skillId: string;
  name: string;
  demand: number;
  change: number;
}
export interface SkillGap {
  skillId: string;
  name: string;
  demand: number;
  status: "none" | "learning-only" | "career-only";
  trend: number;
}
export interface JobPosting {
  id: string;
  company: string;
  position: string;
  category: RoleId;
  skills: string[];
  postedAt: string;
  url: string;
  location: string;
  color: string;
}
export interface RecommendedAction {
  id: string;
  role: RoleId;
  title: string;
  description: string;
  type: EvidenceType;
  skillIds: string[];
  duration: string;
  steps: string[];
}
export type ActionStatus = "suggested" | "active" | "completed";
export type ApplicationStage =
  "Applied" | "Document" | "Coding Test" | "Interview" | "Final";
export interface ResumeVersion {
  id: string;
  name: string;
  version: string;
  updatedAt: string;
}
export interface Application {
  id: string;
  jobId: string;
  resumeId: string;
  stage: ApplicationStage;
  appliedAt: string;
  skillSnapshot: string[];
  result: string;
  questions: string[];
  timeline: { stage: ApplicationStage; date: string; note: string }[];
}
export interface MarketDataset {
  skills: MarketSkill[];
  total: number;
  trend: { month: string; [skill: string]: number | string }[];
  relationships: string[][];
}
export interface CareerDataset {
  roles: Role[];
  skills: Skill[];
  evidence: Evidence[];
  jobs: JobPosting[];
  market: Record<RoleId, MarketDataset>;
  actions: RecommendedAction[];
  applications: Application[];
  resumes: ResumeVersion[];
}
export interface Connection {
  source: EvidenceSource;
  label: string;
  connected: boolean;
}
export interface ProfileState {
  name: string;
  role: RoleId;
  targetRoles: RoleId[];
  connections: Connection[];
  actionStatus: Record<string, ActionStatus>;
  addedEvidence: Evidence[];
  applications: Application[];
  analyzedAt: string;
  onboarded: boolean;
}
export interface CareerService {
  mode: "demo" | "live";
  getDataset(): Promise<CareerDataset>;
  getJobs(): Promise<JobPosting[]>;
  analyzeJob(query: string): Promise<JobPosting | null>;
}
