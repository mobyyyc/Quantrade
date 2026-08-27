# Regime-Interaction Feature Audit

## Decision

P9A.3 passes. The two pre-registered SPY regime-interaction features were
materialized on development data only. No challenger was fitted, the locked
holdout was not opened, and the active model was not changed.

## Coverage

- Rows: 341,944 of 341,944
- Aggregate coverage: 100.00%
- Minimum formation coverage: 100.00%
- Formations: 875 of 875
- Date span: 2022-01-03 through 2025-06-30
- Point-in-time violations: 0

## Market regimes

- Bearish formations: 160
- Range-bound formations: 410
- Bullish formations: 305

## Feature ranges

- `momentum_12_1_market_trend_interaction_v1`: -0.3134839484532736066478397766 to 0.3134839484532736066478397766
- `relative_strength_6m_market_trend_interaction_v1`: -0.3134839484532736066478397766 to 0.3134839484532736066478397766

## Provenance

- Source dataset SHA-256: `92c67bf2367c0624e81f0c05016db467dcfed0bcb382bf7f83345c7297c47cc3`
- Interaction-definition SHA-256: `e70cbfbbbe6f27f115f606ec3f67863b1adec4b7afc1e3fa7f9448de8ccc7e11`
- Combined feature-registry SHA-256: `fbba8491fc59568e180e29d9d416dfe0e29e5d85c019234cc8765439c6cfdfcb`
- SPY lineage SHA-256: `c7950851aa3c9eeab93a6e2800c82ea12abd52961d6bfb934cf674608bd68444`
- Materialized dataset SHA-256: `55f62409712122b00fc219c182f99924ab92ffb75ac7b475c15a7cd2df7d1957`

## Reproducibility

Two independent materializations produced byte-identical CSV datasets,
manifests, and audit reports. Their file SHA-256 values were respectively
`55f62409712122b00fc219c182f99924ab92ffb75ac7b475c15a7cd2df7d1957`,
`2651e087396bfc89b4bfdd85af9a5cca2f3b86776a558d6909a64e1d816c1895`,
and `10083634a1311f25f2bfad6dec893474b6b9b193f6b195d47458fc1253ac7df3`.

The dataset remains Tier-B survivorship-biased private research. Passing this
audit authorizes only the pre-registered development comparison in P9A.4.
It does not establish that the challenger is useful or eligible for freezing.
