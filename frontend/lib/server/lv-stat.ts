import "server-only";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type {
  LvCategoryCode,
  LvJob,
  LvJobStage,
  LvJobStatus,
  LvProfile,
} from "@/types/lv-stat";

// 스테이징 LV 서비스에서 웹 쪽 파일 저장소. 웹과 분석 작업자(lv-stat/service)는 <CAREER_DATA_DIR>/lv-stat
// 아래 파일로 주고받는다(lv-stat/service/CONTRACT.md). 작업자는 웹과 같은 OS 사용자로 돈다.
// 파일 이름은 서버가 만든 값(요청 uuid, profileKey)으로만 짓는다.

export class LvStatError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

// 스테이징 스위치: 서버 설정 CAREER_LV_STAT가 정확히 'on'일 때만 켠다. 스테이징 웹 유닛만 on이고 운영(main)은 off다
// (deploy/web/deploy.sh). 꺼져 있으면 분석 API는 404이고 공고 화면은 분석 결과를 읽지 않는다. 작업자가 없는 운영에서
// 요청이 '대기'로 영영 남지 않게 한다. 빌드할 때나 불러올 때 굳지 않게 요청 때마다 읽는다.
export function lvStatEnabled() {
  return process.env.CAREER_LV_STAT === "on";
}

// store.ts의 db()와 같은 기준. 시험이 바꿀 수 있게 부를 때마다 환경 변수를 읽는다.
export function lvDataDir() {
  return path.join(
    process.env.CAREER_DATA_DIR || path.join(process.cwd(), ".career-data"),
    "lv-stat",
  );
}

// 결과 파일 이름(작업자 profile_key와 같음): sha256(namespace + ":" + subjectId)의 16진수 앞 32자.
export function profileKey(namespace: string, subjectId: string) {
  return createHash("sha256")
    .update(`${namespace}:${subjectId}`)
    .digest("hex")
    .slice(0, 32);
}

// GitHub 아이디 규칙(작업자와 같음): 영문·숫자, '-'는 그 사이에 하나씩, 39자 이하.
const loginPattern = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
// https://github.com/<아이디>[/<레포>][/] 꼴만 받는다(www. 허용, 스킴·호스트 대소문자 무관). 입력 전체가
// 이 꼴이어야 하므로 사용자·암호(@)·포트(:)·쿼리(?)·조각(#)·공백·더 깊은 경로가 있으면 맞지 않는다.
// 레포 이름은 GitHub 규칙(영문·숫자·_·.·-, 100자 이하)이라 끝의 .git도 여기에 든다.
const githubUrl =
  /^https:\/\/(?:www\.)?github\.com\/([^/]+)(?:\/[\w.-]{1,100})?\/?$/i;

export function parseGithubLogin(input: string): string | null {
  const login = githubUrl.exec(input)?.[1];
  return login && loginPattern.test(login) ? login : null;
}

const statuses: readonly LvJobStatus[] = [
  "queued",
  "running",
  "done",
  "failed",
];
const stages: readonly LvJobStage[] = [
  "대기",
  "레포 찾기",
  "레포 받기",
  "색인",
  "규칙 적용",
  "계산",
  "끝",
  "실패",
];
// 요청 파일 이름은 uuid v4 + .json뿐이다(작업자 list_jobs와 같음). 임시 파일과 다른 이름은 읽지 않는다.
const jobName =
  /^([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\.json$/;
// 「Claude 임시값」 전체 대기(queued) 요청은 20건까지 받는다.
const maxQueued = 20;

const jobsDir = () => path.join(lvDataDir(), "jobs");

// 같은 사람 확인과 파일 쓰기 사이에 다른 요청이 끼지 않게 createJob을 하나씩 돌린다. 스테이징 웹은
// 프로세스 하나라 프로세스 안의 사슬로 충분하다. store.ts의 연결처럼 globalThis에 두어 사슬이 하나다.
const shared = globalThis as unknown as { careerLvJobChain?: Promise<unknown> };
function oneAtATime<T>(task: () => Promise<T>): Promise<T> {
  const run = (shared.careerLvJobChain ?? Promise.resolve()).then(task);
  shared.careerLvJobChain = run.catch(() => undefined);
  return run;
}

export async function createJob(request: {
  namespace: string;
  subjectId: string;
  login: string;
  input: string;
}): Promise<LvJob> {
  const { namespace, subjectId, login, input } = request;
  return oneAtATime(async () => {
    const jobs = await readJobs();
    // 「Claude 임시값」 사람(namespace+subjectId)마다 진행 중(queued·running) 요청은 1건이다.
    if (
      jobs.some(
        (job) =>
          job.namespace === namespace &&
          job.subjectId === subjectId &&
          (job.status === "queued" || job.status === "running"),
      )
    )
      throw new LvStatError(
        "이미 분석 중이에요. 끝나면 다시 시도해 주세요.",
        409,
      );
    if (jobs.filter((job) => job.status === "queued").length >= maxQueued)
      throw new LvStatError(
        "지금 분석 요청이 많아요. 잠시 뒤 다시 시도해 주세요.",
        503,
      );
    const job: LvJob = {
      id: randomUUID(),
      namespace,
      subjectId,
      login,
      input,
      status: "queued",
      createdAt: new Date().toISOString(),
    };
    // CONTRACT: 같은 폴더의 임시 파일에 쓴 뒤 rename으로 바꾼다. 임시 파일 이름은 점으로 시작해
    // 요청 파일 이름 규칙에 맞지 않으므로 웹도 작업자도 요청으로 읽지 않는다.
    const dir = jobsDir();
    await mkdir(dir, { recursive: true, mode: 0o700 });
    const temp = path.join(dir, `.${job.id}.tmp`);
    await writeFile(temp, JSON.stringify(job), { mode: 0o600 });
    await rename(temp, path.join(dir, `${job.id}.json`));
    return job;
  });
}

// 그 사람(namespace+subjectId)의 요청 중 createdAt이 가장 늦은 것.
export async function latestJob(
  namespace: string,
  subjectId: string,
): Promise<LvJob | null> {
  let latest: LvJob | null = null;
  for (const job of await readJobs())
    if (
      job.namespace === namespace &&
      job.subjectId === subjectId &&
      (!latest || Date.parse(job.createdAt) > Date.parse(latest.createdAt))
    )
      latest = job;
  return latest;
}

// 그 사람의 마지막 분석 결과. 파일 이름은 profileKey뿐이고, 파일이 없거나 깨졌거나, 안의 사람이 다르거나,
// CONTRACT 모양이 아니면 null이다(scoreKeyword와 화면이 모양을 믿고 읽는다).
export async function readProfile(
  namespace: string,
  subjectId: string,
): Promise<LvProfile | null> {
  const value = await readJson(
    path.join(
      lvDataDir(),
      "profiles",
      `${profileKey(namespace, subjectId)}.json`,
    ),
  );
  if (value === null) return null;
  if (isProfileOf(value, namespace, subjectId)) return value;
  // 있는 파일을 모양 때문에 버린다. 첫 배포에서 작업자와 약속이 어긋나면 보이게 서버 기록에 한 줄 남긴다(경로·내용은 남기지 않음).
  console.error("LV profile ignored", { error: "ShapeMismatch" });
  return null;
}

async function readJobs(): Promise<LvJob[]> {
  const dir = jobsDir();
  let names: string[];
  try {
    names = await readdir(dir);
  } catch (error) {
    if (isMissing(error)) return [];
    throw error;
  }
  const jobs = await Promise.all(
    names.map(async (name) => {
      const id = jobName.exec(name)?.[1];
      return id ? toJob(await readJson(path.join(dir, name)), id) : null;
    }),
  );
  return jobs.filter((job) => job !== null);
}

// 요청 파일을 CONTRACT 칸만으로 다시 짠다. 웹이 쓴 칸이 틀리면 null이다. 작업자가 더하는 칸은
// 모양이 맞을 때만 옮겨서, 그 칸 하나가 틀려도 요청은 그대로 진행 중으로 센다.
function toJob(value: unknown, id: string): LvJob | null {
  if (!isRecord(value) || value.id !== id) return null;
  const { namespace, subjectId, login, input, status, createdAt } = value;
  if (
    typeof namespace !== "string" ||
    typeof subjectId !== "string" ||
    typeof login !== "string" ||
    typeof input !== "string" ||
    !isOneOf(statuses, status) ||
    !isTime(createdAt)
  )
    return null;
  const job: LvJob = {
    id,
    namespace,
    subjectId,
    login,
    input,
    status,
    createdAt,
  };
  if (isOneOf(stages, value.stage)) job.stage = value.stage;
  if (value.progress === null || isProgress(value.progress))
    job.progress = value.progress;
  for (const key of [
    "startedAt",
    "finishedAt",
    "error",
    "profileKey",
  ] as const) {
    const field = value[key];
    if (typeof field === "string") job[key] = field;
  }
  return job;
}

const categoryCodes: readonly LvCategoryCode[] = [
  "L",
  "O",
  "B",
  "E",
  "D",
  "F",
  "A",
];

function isProfileOf(
  value: unknown,
  namespace: string,
  subjectId: string,
): value is LvProfile {
  if (
    !isRecord(value) ||
    value.schema !== "lv-stat-profile/1" ||
    value.namespace !== namespace ||
    value.subjectId !== subjectId
  )
    return false;
  const { repos, categories } = value;
  return (
    typeof value.method === "string" &&
    isStrings(value.labels) &&
    typeof value.login === "string" &&
    typeof value.jobId === "string" &&
    isTime(value.analyzedAt) &&
    isRecord(repos) &&
    isCount(repos.found) &&
    isCount(repos.analyzed) &&
    isCount(repos.failed) &&
    isStrings(repos.notes) &&
    isRecord(categories) &&
    categoryCodes.every((code) => isCategory(categories[code])) &&
    isProgramming(categories.L)
  );
}

// lv는 0.0~5.0 또는 null(판정 불가), unknown은 '모름 n개'의 n.
function isCategory(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.name === "string" &&
    (value.lv === null || isLevel(value.lv)) &&
    isCount(value.unknown)
  );
}

// L은 언어 이름 → 그 언어 LV와 가장 높은 언어(없으면 null)가 더 있다.
function isProgramming(value: unknown) {
  return (
    isRecord(value) &&
    isRecord(value.languages) &&
    Object.values(value.languages).every(isLevel) &&
    (value.best === null || typeof value.best === "string")
  );
}

function isProgress(value: unknown): value is { done: number; total: number } {
  return isRecord(value) && isCount(value.done) && isCount(value.total);
}

const isLevel = (value: unknown) =>
  typeof value === "number" && value >= 0 && value <= 5;
const isCount = (value: unknown) =>
  typeof value === "number" && Number.isInteger(value) && value >= 0;
const isTime = (value: unknown): value is string =>
  typeof value === "string" && !Number.isNaN(Date.parse(value));
const isStrings = (value: unknown) =>
  Array.isArray(value) && value.every((item) => typeof item === "string");

function isOneOf<T extends string>(
  list: readonly T[],
  value: unknown,
): value is T {
  return (list as readonly unknown[]).includes(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const isMissing = (error: unknown) =>
  error instanceof Error && (error as NodeJS.ErrnoException).code === "ENOENT";

// 파일이 없거나 JSON이 깨졌으면 null. 그 밖의 읽기 오류(권한 등)는 그대로 던진다.
async function readJson(file: string): Promise<unknown> {
  let text: string;
  try {
    text = await readFile(file, "utf8");
  } catch (error) {
    if (isMissing(error)) return null;
    throw error;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
