import "server-only";

import { createHash, randomBytes, randomUUID, scrypt, timingSafeEqual, type ScryptOptions } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { databasePool } from "@/lib/research-read-model";

export const SESSION_COOKIE_NAME = "quantrade_session";
const SESSION_SECONDS = 60 * 60 * 12;
const PASSWORD_MINIMUM_LENGTH = 12;

export type AuthenticatedUser = { userId: string; email: string; role: "owner" | "member" };

function sha256(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

export function normalizedEmail(value: string) {
  return value.trim().toLocaleLowerCase("en-US");
}

export function validPassword(value: string) {
  return value.length >= PASSWORD_MINIMUM_LENGTH && value.length <= 256;
}

function derivePassword(password: string, salt: Buffer, length: number, options: ScryptOptions) {
  return new Promise<Buffer>((resolve, reject) => {
    scrypt(password, salt, length, options, (error, derived) => error ? reject(error) : resolve(derived));
  });
}

export async function hashPassword(password: string) {
  if (!validPassword(password)) throw new Error(`Password must be ${PASSWORD_MINIMUM_LENGTH}–256 characters.`);
  const salt = randomBytes(16);
  const derived = await derivePassword(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$16384$8$1$${salt.toString("base64url")}$${derived.toString("base64url")}`;
}

export async function verifyPassword(password: string, encoded: string) {
  const [algorithm, n, r, p, saltValue, hashValue] = encoded.split("$");
  if (algorithm !== "scrypt" || n !== "16384" || r !== "8" || p !== "1" || !saltValue || !hashValue) return false;
  try {
    const expected = Buffer.from(hashValue, "base64url");
    const actual = await derivePassword(password, Buffer.from(saltValue, "base64url"), expected.length, {
      N: Number(n), r: Number(r), p: Number(p),
    });
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  } catch {
    return false;
  }
}

export function requestSubject(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || request.headers.get("x-real-ip") || "unknown";
  return sha256(`ip:${address}`);
}

export function isLoopbackRequest(request: Request) {
  const host = new URL(request.url).hostname.toLocaleLowerCase();
  const isLoopback = (value: string) => value === "127.0.0.1" || value === "localhost" || value === "::1" || value === "[::1]" || value === "::ffff:127.0.0.1";
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim().toLocaleLowerCase();
  return isLoopback(host) && (!forwarded || isLoopback(forwarded));
}

export function requireSameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) throw new AuthError("Request origin is required.", 403);
  const incoming = new URL(origin);
  const requestUrl = new URL(request.url);
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const host = forwardedHost || request.headers.get("host") || requestUrl.host;
  const protocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim() || requestUrl.protocol.replace(":", "");
  const expected = new URL(`${protocol}://${host}`);
  if (incoming.origin === expected.origin) return;
  const loopback = (hostname: string) => hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
  if (loopback(incoming.hostname) && loopback(expected.hostname) && incoming.port === expected.port) return;
  throw new AuthError("Cross-origin request denied.", 403);
}

export class AuthError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function hasAnyUsers() {
  const result = await databasePool().query("SELECT EXISTS (SELECT 1 FROM quantrade.app_users WHERE disabled_at IS NULL) AS present");
  return Boolean(result.rows[0]?.present);
}

export async function createOwner(email: string, password: string) {
  const normalized = normalizedEmail(email);
  if (!/^\S+@\S+\.\S+$/.test(normalized)) throw new AuthError("Enter a valid email address.", 400);
  if (!validPassword(password)) throw new AuthError(`Use at least ${PASSWORD_MINIMUM_LENGTH} characters.`, 400);
  const passwordHash = await hashPassword(password);
  const client = await databasePool().connect();
  try {
    await client.query("BEGIN");
    await client.query("SELECT pg_advisory_xact_lock(hashtext('quantrade_owner_setup'))");
    const existing = await client.query("SELECT 1 FROM quantrade.app_users LIMIT 1 FOR UPDATE");
    if (existing.rowCount) throw new AuthError("Owner setup is already complete.", 409);
    const result = await client.query(
      `INSERT INTO quantrade.app_users (email, normalized_email, password_hash, role)
       VALUES ($1, $2, $3, 'owner') RETURNING user_id::text, email, role`,
      [email.trim(), normalized, passwordHash],
    );
    await client.query("COMMIT");
    return { userId: String(result.rows[0].user_id), email: String(result.rows[0].email), role: result.rows[0].role } as AuthenticatedUser;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally { client.release(); }
}

export async function authenticate(email: string, password: string): Promise<AuthenticatedUser | null> {
  const result = await databasePool().query(
    `SELECT user_id::text, email, role, password_hash FROM quantrade.app_users
     WHERE normalized_email = $1 AND disabled_at IS NULL`,
    [normalizedEmail(email)],
  );
  const row = result.rows[0];
  if (!row) {
    await derivePassword(password, Buffer.alloc(16), 64, { N: 16384, r: 8, p: 1 });
    return null;
  }
  if (!await verifyPassword(password, String(row.password_hash))) return null;
  return { userId: String(row.user_id), email: String(row.email), role: row.role };
}

export async function createSession(userId: string) {
  const token = randomBytes(32).toString("base64url");
  await databasePool().query(
    `WITH expired AS (
       DELETE FROM quantrade.app_sessions WHERE user_id = $1 AND (expires_at <= now() OR revoked_at IS NOT NULL)
     )
     INSERT INTO quantrade.app_sessions (user_id, token_sha256, expires_at)
     VALUES ($1, $2, now() + ($3 * interval '1 second'))`,
    [userId, sha256(token), SESSION_SECONDS],
  );
  return token;
}

export async function setSessionCookie(token: string, request: Request) {
  (await cookies()).set(SESSION_COOKIE_NAME, token, {
    httpOnly: true, sameSite: "strict", secure: new URL(request.url).protocol === "https:",
    path: "/", maxAge: SESSION_SECONDS, priority: "high",
  });
}

export async function deleteSession(token?: string) {
  if (token) await databasePool().query("UPDATE quantrade.app_sessions SET revoked_at = now() WHERE token_sha256 = $1", [sha256(token)]);
  (await cookies()).delete(SESSION_COOKIE_NAME);
}

async function userForToken(token?: string): Promise<AuthenticatedUser | null> {
  if (!token) return null;
  const result = await databasePool().query(
    `UPDATE quantrade.app_sessions session SET last_seen_at = now()
     FROM quantrade.app_users app_user
     WHERE session.token_sha256 = $1 AND session.user_id = app_user.user_id
       AND session.revoked_at IS NULL AND session.expires_at > now() AND app_user.disabled_at IS NULL
     RETURNING app_user.user_id::text, app_user.email, app_user.role`,
    [sha256(token)],
  );
  const row = result.rows[0];
  return row ? { userId: String(row.user_id), email: String(row.email), role: row.role } : null;
}

export async function authenticatedUser(): Promise<AuthenticatedUser | null> {
  return userForToken((await cookies()).get(SESSION_COOKIE_NAME)?.value);
}

export async function requireAuthenticatedUser() {
  const user = await authenticatedUser();
  if (!user) redirect("/sign-in");
  return user;
}

export async function requireApiUser(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const token = cookieHeader.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${SESSION_COOKIE_NAME}=`))?.slice(SESSION_COOKIE_NAME.length + 1);
  const user = await userForToken(token);
  if (!user) throw new AuthError("Authentication required.", 401);
  return user;
}

export async function authorizeApiRequest(request: Request, scope = "api_read", limit = 240, windowSeconds = 60) {
  const user = await requireApiUser(request);
  const rate = await consumeRateLimit(scope, user.userId, limit, windowSeconds);
  if (!rate.allowed) throw new AuthError("Too many requests. Try again shortly.", 429);
  return user;
}

export async function consumeRateLimit(scope: string, subject: string, limit: number, windowSeconds: number) {
  const result = await databasePool().query(
    `WITH expired AS (
       DELETE FROM quantrade.web_rate_limit_windows WHERE expires_at < now() - interval '1 day'
     )
     INSERT INTO quantrade.web_rate_limit_windows
       (scope, subject_sha256, window_started_at, request_count, expires_at)
     VALUES ($1, $2, to_timestamp(floor(extract(epoch FROM now()) / $3) * $3), 1,
             to_timestamp((floor(extract(epoch FROM now()) / $3) + 1) * $3))
     ON CONFLICT (scope, subject_sha256, window_started_at)
     DO UPDATE SET request_count = quantrade.web_rate_limit_windows.request_count + 1
     RETURNING request_count, extract(epoch FROM expires_at)::bigint AS reset_at`,
    [scope, subject, windowSeconds],
  );
  const count = Number(result.rows[0].request_count);
  return { allowed: count <= limit, remaining: Math.max(0, limit - count), resetAt: Number(result.rows[0].reset_at) };
}

export async function auditEvent(input: {
  requestId?: string; userId?: string; eventType: string; outcome: "allowed" | "denied" | "failed";
  route: string; subject?: string; metadata?: Record<string, string | number | boolean>;
}) {
  await databasePool().query(
    `INSERT INTO quantrade.web_audit_events
       (request_id, user_id, event_type, outcome, route, subject_sha256, metadata)
     VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)`,
    [input.requestId ?? randomUUID(), input.userId ?? null, input.eventType, input.outcome,
      input.route, input.subject ?? null, JSON.stringify(input.metadata ?? {})],
  );
}

export function authErrorResponse(error: unknown) {
  const status = error instanceof AuthError ? error.status : 500;
  const message = error instanceof AuthError ? error.message : "The request could not be authorized.";
  return Response.json({ error: message }, { status });
}
