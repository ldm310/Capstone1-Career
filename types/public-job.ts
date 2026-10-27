import type { SupportedRole as RoleId } from "@/lib/roles";
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
  dummy?: boolean;
  posting?: PostingSection[];
}
export interface PostingSection {
  title: string;
  items: string[];
}
export interface PublicJobsResponse {
  jobs: PublicJob[];
  total: number;
  nextOffset: number | null;
  checkedAt: string;
  unavailableSources: string[];
}
