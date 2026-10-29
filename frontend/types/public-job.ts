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
  details?: JobDetails;
}
// 공고 상세 화면의 요약 정보. 원문에 없는 값은 비워 두고 화면에서도 숨긴다.
export interface JobDetails {
  education?: string;
  salary?: string;
  position?: string;
  headcount?: string;
  address?: string;
  station?: string;
  startsAt?: string;
  applyMethod?: string;
  documents?: string[];
  company?: CompanyInfo;
}
export interface CompanyInfo {
  ceo?: string;
  type?: string;
  industry?: string;
  employees?: string;
  founded?: string;
  revenue?: string;
  homepage?: string;
  address?: string;
}
// 근무지를 모르는 공고(백엔드 공고 등)의 location. 목록에는 그대로 쓰고 상세의 근무지 위치는 숨긴다.
export const unknownLocation = "근무지 원문 확인";
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
