# Phase 9C Data Feasibility Decision

Decision key: `phase_9c_data_feasibility_v1`

Decision date: 2026-08-28

Status: **restricted; proceed with P9C.2 and P9C.3, but do not build or fit the
Phase 9C model dataset yet**

## Scope and reproducibility

The audit inspected the existing PostgreSQL store in a read-only transaction.
It made no network request, downloaded no data, mutated no table, joined no
candidate outcome, and did not inspect the consumed holdout.

Reproduction command:

```powershell
$env:PYTHONPATH='services/research/src'
py -3.14 -m quantrade_research.phase_9c_data_feasibility --env-file .env --output data/derived/reports/phase_9c_data_feasibility_v1.json
```

Generated report SHA-256:
`6a18d8aaa942788f46e890fd03014872a10c388093ff251db952abdb2440633c`

The generated JSON remains a local derived artifact. This decision record and
the audit implementation preserve its material evidence and make it
reproducible from the current database.

## Evidence and decisions

### Corporate-action-aware wealth label: restricted

- Raw and split-adjusted equity bars cover all 500 cohort members.
- Split-adjusted SPY has 1,419 sessions beginning 2021-01-04.
- The development window contains 6,835 ordinary cash dividends, 46 forward
  splits, and one reverse split.
- It also contains 122 complex actions in the explicitly unresolved classes.
- Provider total-return-adjusted bars cover all 500 names only from 2025-07-01,
  after the Phase 9C development period begins.

Decision: P9C.2 will build one deterministic wealth ledger for ordinary cash
dividends and splits for stocks and SPY. It cannot use the short provider
total-return history as the primary development label. Every label crossing an
unresolved complex action is withheld.

### Point-in-time quarterly and TTM data: restricted

Candidate Q1/H1/9M/FY component-set coverage for fiscal years 2020–2025 is:

| Concept | Securities with at least one candidate complete set |
| --- | ---: |
| Operating cash flow | 486 |
| Net income | 446 |
| Profit/loss alternative | 330 |
| Revenue from contract with customer | 310 |
| Legacy `Revenues` | 234 |
| Direct gross profit | 179 |

These counts prove feasibility only. They do not prove that concept, unit,
duration, fiscal context, accession, and dimensions are compatible.

Decision: P9C.3 may implement true TTM net income/profit-loss and operating
cash flow, plus compatible balance-sheet endpoints. Direct gross profitability
is excluded from the initial Phase 9C family because its candidate complete-set
coverage is too low. Revenue-based reconstruction is not admitted until the
builder proves same-context components without mixing concepts silently.

The immutable future-observation table currently has zero rows. This is
consistent with the lean architecture: frozen legacy canonical facts remain
append-only, while that table records only a changed future ingestion
observation. It does not convert legacy facts into independently observed
point-in-time revisions.

### Endpoint shares: restricted

- Dated endpoint-share facts cover 449 of 500 securities in the bounded audit.
- Period-average basic shares cover 484, but they are not endpoint shares.

Decision: primary Phase 9C issuance and market-cap construction may use only
dated endpoint shares with a proven split/structural-action path. Weighted
average basic shares remain robustness-only. Missing endpoint shares produce a
neutral missing feature with an explicit reason; they are not repaired.

### Historical SIC/FF12: deferred

No accession-dated SIC field is normalized in the current Quantrade schema.
Current static sectors are not a substitute.

Decision: Phase 9C v1 remains market-wide and does not use an FF12 portfolio
cap. Historical SIC extraction is deferred to an independently approved,
targeted metadata task and cannot delay the primary model research.

### Weekly market features: restricted start, otherwise feasible

- The proposed calendar contains 235 weekly formations from 2021-01-08 through
  2025-06-30.
- Sixty-session features first reach 90% cohort coverage on 2021-04-01.
- 252-session features first reach 90% cohort coverage on 2022-01-07.
- From 2022-01-07 onward, minimum 252-session coverage is 95.6%, leaving 183
  eligible weekly formations through 2025-06-30.
- Thirty-five calendar months have four formations and 19 have five.

Decision: the primary common weekly window starts no earlier than 2022-01-07.
Every calendar month receives total training weight one, divided first among
its weekly formations and then among eligible securities. This prevents
five-week months from receiving more influence than four-week months.

## Frozen admissible scope

Phase 9C v1 admits the following implementation scope before fitting:

1. ordinary-dividend and split-aware stock/SPY wealth labels, with complex
   actions withheld;
2. true-TTM net-income/profit-loss and operating-cash-flow paths, point-in-time
   balance-sheet endpoints, and endpoint-share-only primary market cap;
3. weekly market features beginning no earlier than 2022-01-07;
4. market-wide family ranks only; and
5. neutral missing ranks with explicit raw-feature and family availability.

The first version excludes direct gross profitability, historical SIC/FF12,
weighted-average shares as primary endpoints, and provider total-return bars as
the development label source.

## Frozen coverage gates

The numeric model and portfolio gates in `PHASE_9C_RESEARCH_PROTOCOL.md` are now
frozen without change. The previously unspecified informative-coverage gates
are fixed as follows:

- aggregate score coverage at least 95% and every included weekly formation at
  least 90%;
- every included market-derived family at least 90% informative coverage on
  every included formation;
- every included accounting family at least 80% aggregate informative coverage
  and at least 70% on every included formation;
- every scored security must have at least three informative economic families;
- every raw feature admitted to a family must have at least 70% aggregate
  coverage unless it is explicitly retained as a missingness diagnostic and
  excluded from the model value; and
- 100% lineage for every non-neutral value and every completed label.

No threshold may be relaxed after Phase 9C predictions or outcomes are
inspected. Failure means the dependent feature is removed before fitting or the
entire candidate receives `no-freeze`, according to the frozen protocol.

## Consequence

P9C.1 is complete. The database contains enough raw coverage to implement and
test P9C.2 and P9C.3. It does not yet contain a Phase 9C-ready label or true-TTM
feature layer, so P9C.4 dataset materialization and all model fitting remain
blocked until those two foundations pass their deterministic tests.
