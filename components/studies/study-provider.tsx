"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { z } from "zod";
import {
  studyDemoJobs,
  studyOffers,
  type StudyOffer,
  type StudyTier,
} from "@/lib/study-prototype";

const roomSchema = z.object({
  id: z.string(),
  jobId: z.string(),
  tier: z.enum(["low", "middle", "high"]),
  joinedAt: z.string(),
  completed: z.array(z.number().int().nonnegative()),
  messages: z.array(
    z.object({ id: z.string(), text: z.string(), at: z.string() }),
  ),
  events: z.array(
    z.object({ id: z.string(), title: z.string(), at: z.string() }),
  ),
  resources: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      url: z
        .string()
        .url()
        .refine((v) => /^https?:\/\//.test(v)),
    }),
  ),
});
const schema = z.object({
  applied: z.array(z.string()),
  rooms: z.array(roomSchema),
});
export type StudyRoom = z.infer<typeof roomSchema>;
type State = z.infer<typeof schema>;
const key = "career:study-example:v1";
const empty: State = { applied: [], rooms: [] };
const Context = createContext<{
  state: State;
  ready: boolean;
  error: string;
  apply: (jobId: string, tier: StudyTier) => void;
  join: (offer: StudyOffer) => void;
  update: (
    id: string,
    tier: StudyTier,
    fn: (room: StudyRoom) => StudyRoom,
  ) => void;
} | null>(null);

export function applicationKey(jobId: string, tier: StudyTier) {
  return `${jobId}:${tier}`;
}
export function StudyProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(empty);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    Promise.resolve().then(() => {
      if (!live) return;
      try {
        const raw = localStorage.getItem(key);
        if (raw) setState(schema.parse(JSON.parse(raw)));
      } catch {
        setError(
          "저장한 예시 기록을 읽지 못했어요. 이번 방문에서 새로 체험할 수 있어요.",
        );
      }
      setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {
      /* The visible warning below is set outside a render update. */
      queueMicrotask(() =>
        setError("브라우저 저장이 불가능해 이번 방문 중에만 기록돼요."),
      );
    }
  }, [state, ready]);
  function apply(jobId: string, tier: StudyTier) {
    if (!ready || !studyDemoJobs.some((j) => j.id === jobId)) return;
    const id = applicationKey(jobId, tier);
    setState((s) =>
      s.applied.includes(id) ? s : { ...s, applied: [...s.applied, id] },
    );
  }
  function join(offer: StudyOffer) {
    const job = studyDemoJobs.find((j) => j.id === offer.jobId);
    if (
      !ready ||
      !job ||
      !studyOffers(job, offer.tier).some((o) => o.id === offer.id)
    )
      return;
    setState((s) =>
      !s.applied.includes(applicationKey(offer.jobId, offer.tier)) ||
      s.rooms.some((r) => r.id === offer.id)
        ? s
        : {
            ...s,
            rooms: [
              ...s.rooms,
              {
                id: offer.id,
                jobId: offer.jobId,
                tier: offer.tier,
                joinedAt: new Date().toISOString(),
                completed: [],
                messages: [],
                events: [],
                resources: [],
              },
            ],
          },
    );
  }
  function update(
    id: string,
    tier: StudyTier,
    fn: (r: StudyRoom) => StudyRoom,
  ) {
    setState((s) => ({
      ...s,
      rooms: s.rooms.map((r) => (r.id === id && r.tier === tier ? fn(r) : r)),
    }));
  }
  return (
    <Context.Provider value={{ state, ready, error, apply, join, update }}>
      {children}
    </Context.Provider>
  );
}
export function useStudies() {
  const context = useContext(Context);
  if (!context) throw new Error("StudyProvider is required");
  return context;
}
