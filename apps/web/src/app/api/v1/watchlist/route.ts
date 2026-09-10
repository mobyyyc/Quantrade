import {
  AuthError, auditEvent, authErrorResponse, consumeRateLimit, requestSubject,
  requireApiUser, requireSameOrigin,
} from "@/lib/auth";
import { databasePool } from "@/lib/research-read-model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const maximumEntries = 100;

type WatchlistInput = { securityId?: unknown; note?: unknown; tags?: unknown };

function normalizeEntry(value: WatchlistInput) {
  const securityId = String(value.securityId ?? "");
  if (!uuidPattern.test(securityId)) throw new AuthError("A valid security is required.", 400);
  const note = typeof value.note === "string" ? value.note.trim() : "";
  if (note.length > 240) throw new AuthError("Notes cannot exceed 240 characters.", 400);
  const tags = Array.isArray(value.tags)
    ? [...new Set(value.tags.filter((tag): tag is string => typeof tag === "string").map((tag) => tag.trim()).filter(Boolean))]
    : [];
  if (tags.length > 5 || tags.some((tag) => tag.length > 24)) throw new AuthError("Use up to five tags of 24 characters each.", 400);
  return { securityId, note, tags };
}

async function authorize(request: Request, mutation = false) {
  if (mutation) requireSameOrigin(request);
  const user = await requireApiUser(request);
  const rate = await consumeRateLimit("watchlist", user.userId, mutation ? 60 : 180, 60);
  if (!rate.allowed) throw new AuthError("Too many watchlist requests. Try again shortly.", 429);
  return user;
}

export async function GET(request: Request) {
  try {
    const user = await authorize(request);
    const result = await databasePool().query(
      `SELECT entry.security_id::text, security.issuer_name, listing.ticker,
              entry.note, entry.tags
       FROM quantrade.user_watchlist_entries entry
       JOIN quantrade.securities security ON security.security_id = entry.security_id
       LEFT JOIN LATERAL (
         SELECT ticker FROM quantrade.listings
         WHERE security_id = entry.security_id
         ORDER BY (valid_to IS NULL) DESC, valid_from DESC LIMIT 1
       ) listing ON TRUE
       WHERE entry.user_id = $1
       ORDER BY entry.created_at, entry.security_id`,
      [user.userId],
    );
    return Response.json({ entries: result.rows.map((row) => ({
      securityId: String(row.security_id), issuerName: String(row.issuer_name), ticker: String(row.ticker),
      ...(row.note ? { note: String(row.note) } : {}), ...(row.tags?.length ? { tags: row.tags as string[] } : {}),
    })) }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return authErrorResponse(error); }
}

export async function PUT(request: Request) {
  let user;
  try {
    user = await authorize(request, true);
    const body = await request.json() as { entries?: unknown };
    if (!Array.isArray(body.entries) || body.entries.length > maximumEntries) throw new AuthError(`A watchlist can contain up to ${maximumEntries} companies.`, 400);
    const entries = body.entries.map((entry) => normalizeEntry(entry as WatchlistInput));
    if (new Set(entries.map((entry) => entry.securityId)).size !== entries.length) throw new AuthError("Duplicate watchlist companies are not allowed.", 400);
    const client = await databasePool().connect();
    try {
      await client.query("BEGIN");
      for (const entry of entries) {
        await client.query(
          `INSERT INTO quantrade.user_watchlist_entries (user_id, security_id, note, tags)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (user_id, security_id) DO UPDATE
             SET note = excluded.note, tags = excluded.tags, updated_at = now()`,
          [user.userId, entry.securityId, entry.note, entry.tags],
        );
      }
      await client.query(
        `DELETE FROM quantrade.user_watchlist_entries
         WHERE user_id = $1 AND NOT (security_id = ANY($2::uuid[]))`,
        [user.userId, entries.map((entry) => entry.securityId)],
      );
      await client.query("COMMIT");
    } catch (error) { await client.query("ROLLBACK"); throw error; } finally { client.release(); }
    await auditEvent({ userId: user.userId, eventType: "watchlist_replace", outcome: "allowed", route: "/api/v1/watchlist", subject: requestSubject(request), metadata: { entryCount: entries.length } });
    return Response.json({ saved: entries.length });
  } catch (error) {
    if (user) await auditEvent({ userId: user.userId, eventType: "watchlist_replace", outcome: "failed", route: "/api/v1/watchlist", subject: requestSubject(request) }).catch(() => undefined);
    return authErrorResponse(error);
  }
}
