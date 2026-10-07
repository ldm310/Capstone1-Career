import type { RoleId } from "./career";
export interface PublicJob {
  id: string;
  skills?: string[];
  company: string;
  title: string;
  category: RoleId;
  location: string;
  employment: string;
  workplace: string | null;
  postedAt: string | null;
  closesAt?: string | null;
  experience?: ("entry" | "experienced" | "intern" | "any")[];
  url: string;
}
export interface PublicJobsResponse {
  jobs: PublicJob[];
  total: number;
  nextOffset: number | null;
  checkedAt: string;
  unavailableSources: string[];
}
