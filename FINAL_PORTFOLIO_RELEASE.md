# Final portfolio release

**Decision:** passed for the zero-additional-budget portfolio release

**Release date:** 2026-09-16 America/Toronto

**Release tag:** `v1.0.0-portfolio.1`

**Acceptance baseline:** `6ac2d5e`

**Machine-readable contract:** [`releases/portfolio-v1.json`](releases/portfolio-v1.json)

## Release scope

This release closes Quantrade's active portfolio-project build. It freezes the
working local private beta, deterministic synthetic demo, point-in-time research
pipeline, active model contract, daily operating boundary, recovery procedure,
and technical case study. It does not provision paid infrastructure, authorize
external market-data display, or convert the research output into investment
advice.

## Acceptance evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Independent reproduction | Passed | A disposable `quantrade_demo` database applied all 39 migrations, created 57 Quantrade tables, and loaded the deterministic 20-security synthetic fixture. Its canonical update rehearsal made zero provider requests and zero database writes. |
| Research tests | Passed | 433 Python tests passed. |
| Web quality | Passed | ESLint and the Next.js 16.3.1 production build completed successfully. |
| Browser and accessibility | Passed | All 21 Playwright tests passed across the supported desktop and narrow-screen states. |
| Full-history secret scan | Passed | The scanner found no credential in the tracked tree or Git history. Dynamic PowerShell URI expressions are distinguished from literal credentials by a regression test. |
| Artifact hygiene | Passed | No environment file, provider payload, derived dataset, backup, log, database, key, or generated browser output is tracked. |
| Documentation links | Passed | Every local link in the tracked Markdown documentation resolved. |
| Scheduled-task contracts | Passed | The daily update and PostgreSQL backup tasks use hidden windows, correct launch boundaries, overlap protection, and missed-run recovery. Neither requires Codex or the web application. |
| Backup verification | Passed | `quantdb_20260917T014501900Z.dump` matched its checksum and exposed 402 restore entries. |
| Isolated restore | Passed | The verified backup restored all 57 Quantrade tables into a temporary database, which was removed afterward. |
| Capacity gate | Passed | PostgreSQL used 11.24 GiB, retained project data used 30.17 GiB, and D: retained 227.18 GiB free. No warning or critical threshold fired. |

Run the complete local gate with:

```powershell
.\scripts\verify-final-portfolio-release.ps1
```

Use `-SkipRestore` only for a later documentation-only verification. The release
decision above included the full restore.

## Live operating status at release

The installed task structure is healthy, and the September 10, 11, 14, and 15
daily runs completed successfully. The September 16 attempt did not publish:
SEC EDGAR returned HTTP 403 for that date's daily master index after three
bounded retries. Quantrade recorded the failed SEC stage and stopped before
publication, so no partial or duplicate score set was created.

This provider incident is not a failed repository acceptance gate, but it is an
open local-operations item. The next maintenance task must verify SEC access and
use the existing missed-run recovery path; it must not bypass the publication
lock or invent filing data.

## Frozen technical contract

- Active model: `tier_b_monthly_elastic_net_sec_clean_v3`.
- Cohort: `sp500_current_survivors_v1`, explicitly Tier B.
- Model inputs: six registered; momentum, volatility, and liquidity have
  non-zero coefficients.
- Score meaning: cross-sectional rank from 0 to 100, not an expected return.
- Label: 20-session split-adjusted return relative to SPY.
- Eligibility: `exact_zero_coefficients_v1` with live protocol
  `score_snapshot_exact_zero_v1`.
- Portfolio formation: `monthly_last_session_next_open_v1`.
- Daily launch boundary: terminal, web button, and scheduler all invoke the same
  canonical script and publication lock.

## Accepted limitations

- This is a private, workstation-hosted research system, not a highly available
  public service.
- The current-survivor cohort and present-day sector grouping introduce
  survivorship and classification bias; they are not historical S&P 500
  membership.
- The active signal is small and time-varying. Scores do not guarantee returns
  or SPY outperformance.
- The July 2025 through June 2026 holdout is consumed and cannot be reused for
  model selection.
- Alpaca-derived displays and outputs are not cleared for third-party or public
  display.
- Historical raw artifacts include accepted legacy physical duplication. The
  current compact daily path deduplicates normalized observations and does not
  retain provider response bodies.
- Local availability depends on the workstation, PostgreSQL, network, and
  external providers. The September 16 SEC HTTP 403 is the release-date example
  of that dependency failing safely.

## Recovery and verification

From a clean checkout:

```powershell
git fetch origin --tags
git show --no-patch --decorate v1.0.0-portfolio.1
git rev-parse v1.0.0-portfolio.1^{}
git status --short
```

The tag is immutable and must never be moved. Runtime databases, `.env` files,
provider artifacts, logs, and backups are deliberately outside Git. Application
rollback never reverses migrations or deletes score snapshots; follow
[`RECOVERY_RUNBOOK.md`](RECOVERY_RUNBOOK.md) and preserve the failed evidence.
