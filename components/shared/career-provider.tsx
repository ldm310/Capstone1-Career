"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { normalizeRole, isSupportedRole } from "@/lib/roles";
import { MotionConfig } from "motion/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { careerService } from "@/lib/career-service";
import type {
  CareerDataset,
  Evidence,
  EvidenceSource,
  ProfileState,
  RecommendedAction,
  RoleId,
  Application,
} from "@/types/career";
const STORAGE_KEY = "career-twin:prototype:v1";
const initialProfile: ProfileState = {
  name: "Dongmin",
  role: "data",
  targetRoles: ["data"],
  connections: [
    { source: "github", label: "GitHub 체험 자료", connected: false },
    { source: "cv", label: "CV", connected: false },
    { source: "notion", label: "Notion 체험 자료", connected: false },
    { source: "certificate", label: "자격증", connected: false },
  ],
  actionStatus: {},
  addedEvidence: [],
  applications: [],
  analyzedAt: "2026-09-25T06:00:00Z",
  onboarded: false,
};
interface CareerContextValue {
  data: CareerDataset | null;
  profile: ProfileState;
  evidence: Evidence[];
  loading: boolean;
  error: string | null;
  notice: string;
  notify: (text: string) => void;
  reload: () => void;
  setRole: (role: RoleId) => void;
  updateProfile: (patch: Partial<ProfileState>) => void;
  connect: (source: EvidenceSource, label: string) => void;
  disconnect: (source: EvidenceSource) => void;
  startAction: (id: string) => void;
  completeAction: (action: RecommendedAction) => void;
  addEvidence: (evidence: Evidence) => void;
  saveApplication: (application: Application) => void;
  reset: () => void;
}
const CareerContext = createContext<CareerContextValue | null>(null);
export function CareerProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<CareerDataset | null>(null);
  const [profile, setProfile] = useState(initialProfile);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    careerService
      .getDataset()
      .then(setData)
      .catch(() =>
        setError("체험 데이터를 불러오지 못했습니다. 다시 시도해주세요."),
      )
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const dataset = await careerService.getDataset();
        if (!active) return;
        setData(dataset);
        try {
          const raw = localStorage.getItem(STORAGE_KEY);
          if (raw) {
            const saved = JSON.parse(raw);
            if (
              saved &&
              typeof saved.role === "string" &&
              Array.isArray(saved.connections) &&
              Array.isArray(saved.addedEvidence) &&
              Array.isArray(saved.applications) &&
              typeof saved.name === "string"
            ) {
              setProfile({
                ...initialProfile,
                ...saved,
                role: normalizeRole(saved.role),
                targetRoles: [normalizeRole(saved.role)],
              });
              if (!isSupportedRole(saved.role))
                setNotice(
                  "직무가 데이터·백엔드로 변경되어 기본 직무를 데이터로 표시해요. 목표 직무를 확인해 주세요. 기존 자료는 유지돼요.",
                );
            }
          }
        } catch {
          setNotice("저장된 데이터를 읽지 못해 기본 체험로 시작합니다.");
        }
        setHydrated(true);
      } catch {
        if (active) setError("체험 데이터를 불러오지 못했습니다.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialize();
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
    } catch {
      /* State remains usable when storage is unavailable. */
    }
  }, [profile, hydrated]);
  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timeout);
  }, [notice]);
  const updateProfile = useCallback(
    (patch: Partial<ProfileState>) => setProfile((p) => ({ ...p, ...patch })),
    [],
  );
  const evidence = useMemo(
    () => [...(data?.evidence ?? []), ...profile.addedEvidence],
    [data, profile.addedEvidence],
  );
  const value: CareerContextValue = {
    data,
    profile,
    evidence,
    loading,
    error,
    notice,
    notify: setNotice,
    reload,
    updateProfile,
    setRole: (role) => setProfile((p) => ({ ...p, role, targetRoles: [role] })),
    connect: (source, label) => {
      setProfile((p) => ({
        ...p,
        connections: p.connections.map((c) =>
          c.source === source ? { ...c, connected: true, label } : c,
        ),
      }));
      setNotice(
        "체험 데이터 소스가 준비되었습니다. 실제 계정에 연결하지 않습니다.",
      );
    },
    disconnect: (source) =>
      setProfile((p) => ({
        ...p,
        connections: p.connections.map((c) =>
          c.source === source ? { ...c, connected: false } : c,
        ),
      })),
    startAction: (id) => {
      setProfile((p) => ({
        ...p,
        actionStatus: { ...p.actionStatus, [id]: "active" },
      }));
      setNotice("활동을 시작했습니다. 커리어 코치에서 진행할 수 있습니다.");
    },
    completeAction: (action) => {
      setProfile((p) => {
        if (p.actionStatus[action.id] === "completed") return p;
        const added = action.skillIds.map((skillId) => ({
          id: `action-${action.id}-${skillId}`,
          skillId,
          type: action.type,
          source:
            action.type === "learning"
              ? ("notion" as const)
              : ("github" as const),
          title: `${action.title} · 체험 데이터`,
          description:
            "체험 활동 완료로 추가된 예시 근거입니다. 실제 자료를 검증한 결과가 아닙니다.",
          sourceUrl: null,
          detectedAt: new Date().toISOString(),
          details: action.steps,
        }));
        return {
          ...p,
          actionStatus: { ...p.actionStatus, [action.id]: "completed" },
          addedEvidence: [...p.addedEvidence, ...added],
          analyzedAt: new Date().toISOString(),
        };
      });
      setNotice(
        "체험 역량 근거가 추가되었습니다. 근거 확인 비율와 보완할 역량이 업데이트됩니다.",
      );
    },
    addEvidence: (item) => {
      setProfile((p) => ({
        ...p,
        addedEvidence: [...p.addedEvidence, item],
        analyzedAt: new Date().toISOString(),
      }));
      setNotice("역량 근거를 체험 프로필에 추가했습니다.");
    },
    saveApplication: (application) => {
      setProfile((p) => ({
        ...p,
        applications: [...p.applications, application],
      }));
      setNotice("지원 기록을 저장했습니다. 실제 지원서는 제출하지 않습니다.");
    },
    reset: () => {
      setProfile(initialProfile);
      setNotice("체험 상태를 초기화했습니다.");
    },
  };
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <CareerContext.Provider value={value}>
          {children}
          <div className={`toast ${notice ? "visible" : ""}`} role="status">
            {notice}
          </div>
        </CareerContext.Provider>
      </TooltipProvider>
    </MotionConfig>
  );
}
export function useCareer() {
  const ctx = useContext(CareerContext);
  if (!ctx) throw new Error("CareerProvider is required");
  return ctx;
}
