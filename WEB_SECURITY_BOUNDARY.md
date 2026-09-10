# Web security boundary

Quantrade's web interface is private by default. Research pages, read APIs,
watchlists, and the daily-update launcher require an authenticated database
session. The command-line and scheduled research jobs remain independent of web
authentication.

## Identity and sessions

- The first owner account is created in the browser only from `localhost` or
  `127.0.0.1`. After one account exists, public bootstrap is permanently closed.
- Passwords use Node's scrypt implementation with a random 128-bit salt. The
  database stores only the encoded salt, parameters, and derived hash.
- The browser receives a random 256-bit opaque session token. Only its SHA-256
  digest is stored in PostgreSQL. Sessions expire after 12 hours and can be
  revoked by signing out.
- Session cookies are HTTP-only, SameSite Strict, path-scoped to the application,
  and marked Secure whenever the request uses HTTPS.
- Proxy checks provide an early redirect, while page layouts and route handlers
  perform the authoritative database-backed session check.

## Authorization and isolation

- Every protected API verifies the session independently. Possessing a cookie
  with the right name is not authorization.
- Only an owner may launch the daily research update.
- Watchlist rows use `(user_id, security_id)` as their primary key. Every read,
  insert, update, and delete is scoped to the authenticated `user_id`.
- The previous browser-local watchlist is migrated once after the owner signs in,
  then removed from local storage. PostgreSQL becomes authoritative.

## Request protections

- State-changing browser requests require a same-origin `Origin` header. Localhost
  and `127.0.0.1` are treated as the same loopback origin only when their ports
  match.
- PostgreSQL-backed fixed-window limits cover sign-in, account setup, normal API
  reads, watchlist writes, and daily-update launches. Expired windows are cleaned
  incrementally.
- Authentication responses do not reveal whether an email exists. Unknown-user
  attempts still perform the password derivation work to reduce timing leakage.

## Audit trail

Authentication, sign-out, watchlist replacement, and daily-update launch/result
events are recorded with a request ID, actor when known, outcome, route, and
sanitized metadata. Client addresses are hashed before storage. Passwords,
session tokens, credentials, and raw addresses must never enter audit metadata.
The database rejects updates or deletes to audit rows.

## Operations

After applying migration `0037`, open the app and create the owner account on the
first-run screen. Losing the owner password currently requires a local database
administrator recovery procedure; self-service password reset and external
identity-provider onboarding belong to Phase 16.

Before staging or external access:

1. Serve the app only over HTTPS behind a trusted reverse proxy.
2. Rotate the private-beta Alpaca pair locally and use isolated staging secrets.
3. Use a managed identity provider with MFA for invited external users, or add a
   separately reviewed local account-management and recovery flow.
4. Verify centralized audit retention, database backups, and proxy header trust.
