import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import path from "node:path";
import {
  createHash,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";
import { cookies } from "next/headers";
import { emptyWorkspace, type Workspace } from "@/types/workspace";
const globals = globalThis as unknown as { careerDb?: DatabaseSync };
export function db() {
  if (!globals.careerDb) {
    const dir =
      process.env.CAREER_DATA_DIR || path.join(process.cwd(), ".career-data");
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    const connection = new DatabaseSync(path.join(dir, "career.sqlite"));
    connection.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
 CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT,password TEXT);
 CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,expires INTEGER);
 CREATE TABLE IF NOT EXISTS workspaces(user_id TEXT PRIMARY KEY,data TEXT);
 CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,user_id TEXT,name TEXT,mime TEXT,bytes BLOB,text TEXT);
 CREATE TABLE IF NOT EXISTS shares(token TEXT PRIMARY KEY,user_id TEXT,data TEXT);
 CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,reset INTEGER);`);
    globals.careerDb = connection;
  }
  globals.careerDb.exec(
    "CREATE TABLE IF NOT EXISTS guests(user_id TEXT PRIMARY KEY)",
  );
  return globals.careerDb;
}
export function isGuest(id: string) {
  return !!db().prepare("SELECT user_id FROM guests WHERE user_id=?").get(id);
}
export function passwordHash(
  password: string,
  salt = randomBytes(16).toString("hex"),
) {
  return `${salt}:${scryptSync(password, salt, 64).toString("hex")}`;
}
export function passwordMatches(password: string, stored: string) {
  const [salt, hash] = stored.split(":");
  return timingSafeEqual(
    Buffer.from(hash, "hex"),
    Buffer.from(passwordHash(password, salt).split(":")[1], "hex"),
  );
}
const hash = (s: string) => createHash("sha256").update(s).digest("hex");
export async function user() {
  const token = (await cookies()).get("career_session")?.value;
  if (!token) return null;
  return db()
    .prepare(
      "SELECT users.id,users.email,users.name FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?",
    )
    .get(hash(token), Date.now()) as
    { id: string; email: string; name: string } | undefined;
}
export async function requireUser() {
  const u = await user();
  if (!u) throw new Error("로그인이 필요합니다.");
  return u;
}
export async function session(id: string) {
  db().prepare("DELETE FROM sessions WHERE expires < ?").run(Date.now());
  const token = randomBytes(32).toString("hex");
  db()
    .prepare("INSERT INTO sessions VALUES(?,?,?)")
    .run(hash(token), id, Date.now() + 604800000);
  (await cookies()).set("career_session", token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 604800,
  });
}
export async function logout() {
  const jar = await cookies();
  const token = jar.get("career_session")?.value;
  if (token)
    db().prepare("DELETE FROM sessions WHERE token=?").run(hash(token));
  jar.delete("career_session");
}
export function workspace(id: string): Workspace {
  const row = db()
    .prepare("SELECT data FROM workspaces WHERE user_id=?")
    .get(id) as { data: string } | undefined;
  return row
    ? { ...emptyWorkspace, ...JSON.parse(row.data) }
    : structuredClone(emptyWorkspace);
}
export function saveWorkspace(id: string, data: Workspace) {
  db()
    .prepare(
      "INSERT INTO workspaces VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
    )
    .run(id, JSON.stringify(data));
}
export function originCheck(req: Request) {
  if (
    !req.headers.get("origin") ||
    new URL(req.headers.get("origin")!).host !== req.headers.get("host")
  )
    throw new Error("요청 출처를 확인할 수 없습니다.");
}
export function rateLimit(key: string, max = 12) {
  const row = db()
    .prepare("SELECT count,reset FROM attempts WHERE key=?")
    .get(key) as { count: number; reset: number } | undefined;
  if (row && row.reset > Date.now() && row.count >= max)
    throw new Error("요청이 많습니다. 15분 후 다시 시도해 주세요.");
  db()
    .prepare(
      "INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN reset<? THEN 1 ELSE count+1 END,reset=CASE WHEN reset<? THEN excluded.reset ELSE reset END",
    )
    .run(key, Date.now() + 900000, Date.now(), Date.now());
}
export async function jsonBody(req: Request) {
  const text = await req.text();
  if (text.length > 1500000) throw new Error("요청 데이터가 너무 큽니다.");
  return JSON.parse(text);
}
export function failure(error: unknown) {
  return Response.json(
    {
      error:
        error instanceof Error ? error.message : "요청을 처리하지 못했습니다.",
    },
    { status: 400 },
  );
}
