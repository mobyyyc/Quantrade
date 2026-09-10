import {
  AuthError, auditEvent, authErrorResponse, consumeRateLimit, createOwner, createSession,
  hasAnyUsers, isLoopbackRequest, requestSubject, requireSameOrigin, setSessionCookie,
} from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const subject = requestSubject(request);
  try {
    requireSameOrigin(request);
    if (!isLoopbackRequest(request)) throw new AuthError("Owner setup is available only from this computer.", 403);
    const rate = await consumeRateLimit("owner_setup", subject, 5, 15 * 60);
    if (!rate.allowed) return Response.json({ error: "Too many setup attempts. Try again later." }, { status: 429 });
    if (await hasAnyUsers()) return Response.json({ error: "Owner setup is already complete." }, { status: 409 });
    const body = await request.json() as { email?: unknown; password?: unknown };
    const user = await createOwner(String(body.email ?? ""), String(body.password ?? ""));
    const token = await createSession(user.userId);
    await setSessionCookie(token, request);
    await auditEvent({ userId: user.userId, eventType: "owner_setup", outcome: "allowed", route: "/api/v1/auth/setup", subject });
    return Response.json({ user: { email: user.email, role: user.role } }, { status: 201 });
  } catch (error) {
    await auditEvent({ eventType: "owner_setup", outcome: "failed", route: "/api/v1/auth/setup", subject }).catch(() => undefined);
    return authErrorResponse(error);
  }
}
