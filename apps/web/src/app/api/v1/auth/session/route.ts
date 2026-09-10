import { cookies } from "next/headers";
import {
  SESSION_COOKIE_NAME, auditEvent, authErrorResponse, authenticate, authenticatedUser, consumeRateLimit,
  createSession, deleteSession, requestSubject, requireSameOrigin, setSessionCookie,
} from "@/lib/auth";

export const runtime = "nodejs";

export async function GET() {
  const user = await authenticatedUser();
  return user
    ? Response.json({ user: { email: user.email, role: user.role } })
    : Response.json({ error: "Authentication required." }, { status: 401 });
}

export async function POST(request: Request) {
  const subject = requestSubject(request);
  try {
    requireSameOrigin(request);
    const rate = await consumeRateLimit("sign_in", subject, 20, 15 * 60);
    if (!rate.allowed) {
      await auditEvent({ eventType: "sign_in", outcome: "denied", route: "/api/v1/auth/session", subject, metadata: { reason: "rate_limited" } });
      return Response.json({ error: "Too many sign-in attempts. Try again later." }, { status: 429 });
    }
    const body = await request.json().catch(() => ({})) as { email?: unknown; password?: unknown };
    const user = await authenticate(String(body.email ?? ""), String(body.password ?? ""));
    if (!user) {
      await auditEvent({ eventType: "sign_in", outcome: "denied", route: "/api/v1/auth/session", subject, metadata: { reason: "invalid_credentials" } });
      return Response.json({ error: "Email or password is incorrect." }, { status: 401 });
    }
    const token = await createSession(user.userId);
    await setSessionCookie(token, request);
    await auditEvent({ userId: user.userId, eventType: "sign_in", outcome: "allowed", route: "/api/v1/auth/session", subject });
    return Response.json({ user: { email: user.email, role: user.role } });
  } catch (error) {
    return authErrorResponse(error);
  }
}

export async function DELETE(request: Request) {
  try {
    requireSameOrigin(request);
    const user = await authenticatedUser();
    const token = (await cookies()).get(SESSION_COOKIE_NAME)?.value;
    await deleteSession(token);
    await auditEvent({ userId: user?.userId, eventType: "sign_out", outcome: "allowed", route: "/api/v1/auth/session", subject: requestSubject(request) });
    return new Response(null, { status: 204 });
  } catch (error) {
    return authErrorResponse(error);
  }
}
