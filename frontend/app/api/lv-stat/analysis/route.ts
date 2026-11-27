import { demoAccount } from "@/lib/server/demo-account";
import {
  createJob,
  latestJob,
  LvStatError,
  parseGithubLogin,
  readProfile,
} from "@/lib/server/lv-stat";
import { profileNamespace } from "@/lib/server/notices";
import {
  isGuest,
  jsonBody,
  originCheck,
  rateLimit,
  user,
} from "@/lib/server/store";

// 스테이징 LV 서비스: 로그인한 회원이 GitHub 계정 주소를 넣으면 분석 요청 파일을 만들고(작업자가 집는다), GET은
// 그 사람의 마지막 요청과 분석 결과를 준다(lv-stat/service/CONTRACT.md). 요청·결과는 로그인한 본인
// (profileNamespace() + 회원 id) 것만 다루고, 클라이언트가 준 값으로 파일 경로를 만들지 않는다.
export const runtime = "nodejs";

const headers = { "Cache-Control": "private, no-store" };
const reply = (status: number, body: object) =>
  Response.json(body, { status, headers });
const refuse = (status: number, error: string) => reply(status, { error });

const signIn = "로그인이 필요합니다.";
const urlHelp = "GitHub 계정 주소를 넣어 주세요. 예: https://github.com/아이디";
// store.ts rateLimit이 한도를 넘었을 때 던지는 글. 그 밖의 오류(DB 등)는 500으로 간다.
const limited = "요청이 많습니다. 15분 후 다시 시도해 주세요.";

export async function GET() {
  try {
    const current = await user();
    if (!current || isGuest(current.id)) return refuse(401, signIn);
    // 데모 계정은 누구나 같이 쓰는 로그인이라 파일을 읽지 않는다(결과는 분석을 요청한 사람에게만 보인다).
    if (current.email === demoAccount.email)
      return reply(200, { job: null, profile: null });
    const namespace = profileNamespace();
    const [job, profile] = await Promise.all([
      latestJob(namespace, current.id),
      readProfile(namespace, current.id),
    ]);
    return reply(200, { job, profile });
  } catch (error) {
    return unexpected(
      "LV analysis lookup failed",
      error,
      "분석 결과를 불러오지 못했어요.",
    );
  }
}

export async function POST(req: Request) {
  try {
    try {
      originCheck(req);
    } catch {
      // Origin이 없거나, 다른 사이트이거나, 주소가 아닌 것(Origin: null)은 모두 같은 403이다.
      return refuse(403, "요청 출처를 확인할 수 없습니다.");
    }
    const current = await user();
    if (!current || isGuest(current.id)) return refuse(401, signIn);
    if (current.email === demoAccount.email)
      return refuse(403, "데모 계정은 GitHub 분석을 할 수 없어요.");
    try {
      rateLimit(`lv-stat:${current.id}`, 6);
    } catch (error) {
      if (error instanceof Error && error.message === limited)
        return refuse(429, limited);
      throw error;
    }
    const input = await requestedUrl(req);
    const login = parseGithubLogin(input);
    if (!login) return refuse(400, urlHelp);
    const job = await createJob({
      namespace: profileNamespace(),
      subjectId: current.id,
      login,
      input,
    });
    return reply(202, { job });
  } catch (error) {
    // createJob이 거절한 것(409 진행 중, 503 전체 대기 상한)은 그 상태와 글 그대로 준다.
    if (error instanceof LvStatError)
      return refuse(error.status, error.message);
    return unexpected(
      "LV analysis request failed",
      error,
      "분석 요청을 처리하지 못했어요.",
    );
  }
}

// 본문 url의 앞뒤 공백을 뺀 것. 본문이 JSON이 아니거나 url이 글이 아니면 빈 글이다(parseGithubLogin이 거절한다).
async function requestedUrl(req: Request) {
  const body: unknown = await jsonBody(req).catch(() => null);
  const url =
    typeof body === "object" && body !== null && "url" in body
      ? body.url
      : null;
  return typeof url === "string" ? url.trim() : "";
}

// 예상하지 못한 오류(파일·DB 읽기 등)는 500이다. 오류 글에는 파일 경로나 DB 주소가 들어가므로 서버 기록에는
// 오류 이름만 남기고, 넣은 주소도 남기지 않는다(my-levels route와 같은 꼴).
function unexpected(log: string, error: unknown, message: string) {
  console.error(log, {
    error: error instanceof Error ? error.name : "UnknownError",
  });
  return refuse(500, message);
}
