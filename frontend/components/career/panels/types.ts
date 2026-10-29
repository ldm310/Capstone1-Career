import type { Dispatch, SetStateAction } from "react";
import type { Workspace, Finding } from "@/types/workspace";
export interface ServerResult {
  workspace?: Workspace;
  url?: string;
  ok?: boolean;
}
export interface PanelProps {
  state: Workspace;
  busy: boolean;
  request: (
    url: string,
    body: unknown,
    method?: string,
  ) => Promise<ServerResult | null>;
  save: (action: string, patch: object) => Promise<ServerResult | null>;
  setNotice: Dispatch<SetStateAction<string>>;
  setError: Dispatch<SetStateAction<string>>;
  findings: Finding[];
  skills: string[];
  targets: string[];
  jobSkills: string[];
  questions: { key: string; text: string; evidence: Finding | undefined }[];
  shares: string[];
  selected: string[];
  setSelected: Dispatch<SetStateAction<string[]>>;
  setShares: Dispatch<SetStateAction<string[]>>;
}
