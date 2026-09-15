# ADR 0001: Staging and Closed-Beta Architecture

- **Status:** Accepted for planning
- **Decision date:** 2026-09-15
- **Decision scope:** Q3.1 only; no cloud resource is authorized or provisioned
- **Release baseline:** `v1.0.0-rc.1`

## Context

Quantrade is a private Windows-hosted Next.js and Python application. The web
process currently reads PostgreSQL directly and launches the canonical research
update by spawning PowerShell. The Python process performs provider ingestion,
point-in-time validation, immutable artifact registration, scoring, portfolio
maintenance, and monitoring. Windows Task Scheduler launches the same update
boundary independently of the web process.

The accepted V1 state measured on 2026-09-15 contains approximately:

- 11.24 GiB in PostgreSQL;
- 7.76 GiB of raw artifacts and 0.91 GiB of derived artifacts;
- 1,535,723 daily price bars and 696,500 immutable score snapshots;
- one scheduled daily update that may run for minutes and must survive a browser
  disconnect, process restart, retry, or duplicate launch.

These facts rule out treating the update as an ordinary web request. The target
must keep interactive requests short, preserve the existing database-backed
idempotency controls, and move durable work to a separately deployable Python
worker.

## Decision drivers

1. Preserve point-in-time data, immutable lineage, and one-publication semantics.
2. Recover a job after worker or network failure without relying on a browser.
3. Keep PostgreSQL, worker, and web latency predictable for a small closed beta.
4. Avoid unnecessary infrastructure and provider boundaries for a solo operator.
5. Support independent web and worker releases with forward-only migrations.
6. Keep the initial bill bounded and provision nothing until Q3.5 approval.
7. Preserve a path to Vercel later if measured frontend needs justify it.

## Decision

Use a **Render-centered, single-region architecture in Ohio** for staging and the
first closed beta. Use Cloudflare R2 for immutable object storage and Clerk for
managed user identity. Instrument both runtimes with structured logs and
OpenTelemetry, exported to Sentry for application errors and traces. Keep every
environment physically separate.

```text
Browser
   |
   v
Render Next.js web service  ---->  Clerk identity
   |       |
   |       +---- enqueue/read ----+
   |                              |
   v                              v
Render PostgreSQL <-------- Python background worker ----> Alpaca / SEC
   ^                              |
   |                              v
short Render cron ---------- Cloudflare R2
  (enqueue only)            (immutable artifacts)
```

Render web, worker, cron, and PostgreSQL must use the same region and private
network. Only the web service is publicly reachable. Clerk and R2 are reached
over TLS. Staging and production must not share a database, bucket, identity
instance, secrets, or service credentials.

### Web service

- Deploy `apps/web` as a Node.js Render web service.
- Keep Server Components and API routes responsible for authenticated reads,
  watchlist mutations, and job enqueue/status only.
- Replace the hosted daily-update child-process route. A web request inserts or
  reuses a durable job and returns its identifier immediately; progress is read
  from PostgreSQL.
- Keep the local PowerShell launcher for local development and workstation
  recovery, but never invoke PowerShell in a hosted request.
- Pin builds to a Git commit. Run migrations as a controlled pre-deploy step,
  never concurrently from multiple web instances.

### Python research worker

- Package `services/research` as a pinned container with health and readiness
  checks and a non-root runtime user.
- Run one background-worker replica initially. It polls the durable job table,
  acquires a lease, runs the existing canonical Python orchestrator, records
  progress, and renews the lease.
- Provider retries remain bounded inside the orchestrator. Whole-job retries are
  owned by the job contract and must not bypass PostgreSQL advisory locks or
  same-date publication checks.
- A crashed worker leaves a resumable job. After the lease expires, another
  attempt continues from immutable receipts and database checkpoints.
- Historical backfills and model training are distinct job types with explicit
  resource limits; they never execute inside the daily-update web path.

### Durable jobs

PostgreSQL is the initial durable queue. This avoids adding Redis before volume
requires it. Q4.2 will add append-only job and attempt records with:

- a versioned job type and payload;
- an idempotency key such as `daily-update:<score-date>`;
- `queued`, `leased`, `succeeded`, `partial`, `failed`, and `cancelled` states;
- lease owner, expiry, heartbeat, attempt count, and bounded retry policy;
- requester/scheduler identity, source Git revision, model/run contracts, and
  correlation ID;
- progress linked to the existing daily research run and event ledger.

Claim work with a short transaction and `FOR UPDATE SKIP LOCKED`. A unique
idempotency constraint prevents manual, scheduled, and retried launches from
creating competing publications. Queue rows coordinate execution; the existing
research ledger remains authoritative for publication truth.

### Scheduling

- Use a short Render cron job to enqueue the weekday update corresponding to
  10:15 p.m. `America/Toronto`. Store the intended IANA time zone and market-day
  rule in the payload; do not derive timing from the host's local clock.
- The cron does no ingestion or scoring and exits after the idempotent enqueue.
- A second schedule enqueues maintenance/retention. Database backups use managed
  PostgreSQL recovery plus separately verified logical exports to object storage.
- Manual web launches and scheduled launches use the same job contract.

Render cron provides run history and a single-active-run rule, but manual
triggering can cancel an active cron. Keeping cron as a very short dispatcher
ensures that this platform behavior cannot cancel the actual research job.

### PostgreSQL

- Use paid Render PostgreSQL; the current 11.24 GiB database does not fit a free
  plan.
- Use separate migration, web-read/write, and worker roles with least privilege.
- Require TLS and use Render's internal connection URL. Set finite connection,
  statement, lock, and idle-transaction timeouts and size pools per service.
- Retain provider-managed point-in-time recovery and create encrypted logical
  exports for independent recovery. Restore drills always target a new database.
- Keep schema migrations forward-only. Deploy schema expansion before code that
  needs it; remove old paths only in a later compatible release.

### Object storage

- Add an S3-compatible artifact-store interface and use Cloudflare R2.
- Address immutable objects by category/date/content hash. Conditional creation
  prevents overwrites; PostgreSQL stores the URI, hash, provider, retrieval time,
  and source lineage.
- Separate buckets per environment. Deny public listing and reads. Grant the
  worker write/read access and the web service no raw-object access by default.
- Store compact provider artifacts, model artifacts, manifests, reports, and
  verified logical backups according to explicit retention classes. Do not copy
  unnecessary source documents.

The current 8.67 GiB artifact set is just below R2's published 10 GB-month free
allowance, but growth and backup retention must be budgeted rather than assumed
free.

### Identity

- Use separate Clerk instances for staging and production.
- Treat Clerk's immutable user identifier as the external identity and map it to
  Quantrade's internal user ID, role, watchlist, and audit records.
- Require verified email, invitation-only onboarding, MFA, recovery, secure
  sessions, and server-side authorization. Provider authentication never replaces
  database authorization or audit events.
- Keep the current local owner/password flow only for local development. Define a
  one-time, auditable owner-account migration before staging.

Clerk's free tier does not include MFA; the cost plan therefore assumes Clerk Pro
for an externally accessible beta.

### Observability

- Emit structured JSON from web and worker with request ID, job ID, attempt ID,
  research run ID, provider, stage, duration, outcome, and source revision.
- Propagate W3C trace context from enqueue through worker execution. Export
  OpenTelemetry traces and errors to Sentry; keep platform logs as a second source.
- Never emit passwords, session tokens, provider keys, database URLs, raw payloads,
  or unrestricted local paths.
- Alert on stale publication, queue age, exhausted retries, missing session,
  provider failure rate, model-health criticals, database/storage growth, failed
  backup, and failed restore drill. Expected market-day no-ops remain quiet.

## Failure and recovery model

| Failure | Expected behavior | Recovery evidence |
| --- | --- | --- |
| Browser disconnects | Enqueued job continues; UI reconnects by job ID. | Job and research event ledgers |
| Web service restarts | Reads/enqueues pause; worker and scheduled jobs continue. | Render deploy/log history |
| Worker crashes | Lease expires; bounded retry resumes idempotently. | Attempt, heartbeat, manifest, and receipt records |
| Duplicate click or cron overlap | Unique key returns the existing job; database publication guards remain final authority. | Idempotency key and advisory-lock evidence |
| Provider outage/rate limit | Bounded retry; fail before publication if validation cannot complete. | Sanitized provider attempt events |
| R2 write failure | Stop before registering an unavailable artifact or publishing dependent scores. | Object hash and database artifact record |
| PostgreSQL outage | Fail closed: no enqueue, reads, or publication. Retry only after connectivity returns. | Managed database events and app telemetry |
| Identity outage | New authentication fails closed; no authorization is inferred from client state. | Clerk and web audit logs |
| Bad web release | Roll web back independently; worker jobs remain durable. | Git SHA and deploy record |
| Bad worker release | Stop/roll worker back to a compatible image; preserve jobs and immutable outputs. | Image SHA, attempts, and release manifest |
| Bad migration/data loss | Do not downgrade in place; restore into an isolated database and cut over after validation. | PITR/export and restore-drill report |

## Alternatives considered

| Option | Strengths | Material failure modes / burden | Planning cost |
| --- | --- | --- | --- |
| **Render web + worker + PostgreSQL; R2; Clerk** | Chosen. Web, worker, and database share one private network; first-class background workers/cron; PostgreSQL PITR; few infrastructure boundaries. | No Canadian region; Next.js lacks Vercel-specific edge integration; Render-region migration requires new services; R2 and Clerk remain external. | Roughly **US$55–100/month** before unusual bandwidth/log volume, depending on web/worker/database sizing. Q3.3 must replace this estimate with measurements. |
| **Vercel web + external worker/database** | Best native Next.js deployment workflow, global CDN, Montréal function region, strong preview experience. | Hosted update cannot spawn the local PowerShell process; the web-to-data path crosses providers/public networking; more secrets, billing surfaces, and correlated failure diagnosis. Vercel Cron does not retry failures and can overlap; it cannot be the execution authority. | Usually the chosen stack plus about **US$20/month** for Vercel Pro, making a likely **US$75–120/month** floor. |
| **Vercel Services / Workflows** | One project and routing surface; durable TypeScript workflows can persist and retry steps. | Services is beta and request-oriented; the existing stateful Python pipeline would need a significant adapter or rewrite. Function duration is finite even after the 2026 increase, and this does not remove the need for managed PostgreSQL/object storage. | Uncertain usage-based compute/workflow charges plus database, storage, and identity. Reject for the first staging cut. |
| **Railway all-in-one** | Low usage-based entry cost; containers, cron, private networking, object storage, and simple monorepo deployment. | Railway PostgreSQL is an official-image service rather than the selected managed-PITR boundary; Hobby volume is capped at 5 GB, below the current database; production reliability and backup operations need more ownership. | Pro has a US$20 minimum including usage; likely lower than the chosen stack, but Q3.3 would need to price compute, database, and recovery controls fairly. |
| **Single VPS with Docker Compose** | Lowest nominal vendor bill and maximal control. | One host is a correlated failure domain; patching, TLS, firewall, backups, monitoring, disk growth, and recovery become owner-operated. It repeats the workstation risk with a public attack surface. | Low invoice, highest operational burden; rejected. |

## Why Vercel is not selected now

Vercel remains a valid future frontend host, but it does not solve Quantrade's
hardest problem: durable, independently recoverable Python research work. Vercel
Cron uses HTTP function invocations, does not retry a failed invocation, and can
start overlapping runs. Vercel Functions now support up to 30 minutes on Pro and
Enterprise, but a longer timeout is not a durable job contract. Vercel Services
is still beta, and adopting Vercel Workflow would move orchestration into
TypeScript rather than package the accepted Python pipeline.

For the first closed beta, one Render data plane gives simpler private networking,
fewer cross-provider failure modes, and a clearer restore path. Reconsider moving
only the web service to Vercel after Q6.4 if measured latency, edge delivery, or
preview-environment needs justify the additional boundary.

## Cost guardrails

The cost figures above are directional as of 2026-09-15, not purchase approval.
Q3.3 must measure web/worker CPU and memory, database working set and growth,
artifact/backup growth, egress, logs, and job duration. Q3.5 must set hard budgets
and approve the exact bill of materials before any paid resource is created.

Relevant published prices at decision time:

- Render lists 512 MB services/workers at US$7/month, 1 GB PostgreSQL at
  US$19/month, expandable database storage at US$0.30/GB, and cron billing with a
  US$1/month minimum.
- Cloudflare R2 Standard lists 10 GB-month free, then US$0.015/GB-month, with free
  egress and metered object operations.
- Clerk lists a free Hobby tier but reserves MFA and configurable session lifetime
  for Pro, starting at US$20/month when billed annually.
- Railway lists a US$20 Pro minimum including US$20 of resource usage, with
  storage, CPU, RAM, and egress metered separately.

## Consequences

### Positive

- The daily update is no longer coupled to a browser, web request, PowerShell, or
  one workstation.
- Web, worker, and database can deploy and roll back independently while sharing a
  private low-latency network.
- One durable database contract reconciles manual launches, schedules, retries,
  progress, and publication truth.
- Object storage and managed identity replace local-only assumptions without
  weakening research provenance or authorization.

### Negative

- Render has no Canadian region; Ohio is the closest available region and Q3.2/Q3.4
  must assess data-rights and privacy implications before external use.
- The solution uses three vendors and incurs a paid floor before inviting users.
- PostgreSQL queue polling is suitable for the planned beta, not unlimited job
  throughput; revisit a dedicated queue only from measured contention or volume.
- Migrating between Render regions requires new resources and an explicit data
  migration.

## Implementation sequence

This ADR changes no runtime. The approved roadmap remains:

1. Q3.2 data-rights audit.
2. Q3.3 measured capacity and cost budget.
3. Q3.4 threat and privacy model.
4. Q3.5 exact staging bill of materials and approval.
5. Q4 package the worker, add the durable job boundary, prepare PostgreSQL and
   R2, adopt managed identity, and separate secrets.
6. Q5 add hosted schedules, distributed idempotency, telemetry, alerts, and
   recovery drills.
7. Q6 provision and validate staging only after those gates pass.

## Sources

- [Render regions](https://render.com/docs/regions)
- [Render private networking](https://render.com/docs/private-network)
- [Render service types](https://render.com/docs/service-types)
- [Render background workers](https://render.com/docs/background-workers)
- [Render cron jobs](https://render.com/docs/cronjobs)
- [Render PostgreSQL recovery and backups](https://render.com/docs/postgresql-backups)
- [Render pricing](https://render.com/pricing)
- [Vercel Services](https://vercel.com/docs/services)
- [Vercel Functions](https://vercel.com/docs/functions)
- [Vercel 30-minute function-duration announcement](https://vercel.com/changelog/vercel-functions-can-now-run-up-to-30-minutes)
- [Vercel Cron management](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
- [Vercel Workflow introduction](https://vercel.com/blog/introducing-workflow)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Clerk pricing](https://clerk.com/pricing)
- [Railway pricing](https://docs.railway.com/pricing/plans)
