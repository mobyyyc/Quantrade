-- Dated universe memberships are source claims, not inferred index history.

BEGIN;

CREATE TABLE quantrade.universe_snapshots (
    universe_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_code TEXT NOT NULL CHECK (universe_code ~ '^[a-z0-9_-]+$'),
    as_of_date DATE NOT NULL,
    historical_membership_verified BOOLEAN NOT NULL DEFAULT FALSE,
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (universe_code, as_of_date, raw_artifact_id)
);

CREATE TABLE quantrade.universe_memberships (
    universe_snapshot_id UUID NOT NULL REFERENCES quantrade.universe_snapshots(universe_snapshot_id),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (universe_snapshot_id, security_id)
);

CREATE INDEX universe_snapshots_as_of_idx
    ON quantrade.universe_snapshots (universe_code, as_of_date DESC);
CREATE INDEX universe_memberships_security_idx
    ON quantrade.universe_memberships (security_id);

COMMIT;
