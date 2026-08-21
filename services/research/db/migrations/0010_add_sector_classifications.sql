-- Dated sector claims used for within-sector quantitative ranking.

BEGIN;

CREATE TABLE quantrade.sector_classifications (
    sector_classification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    sector_code TEXT NOT NULL CHECK (length(sector_code) > 0),
    as_of_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (security_id, as_of_date, source_reference)
);

CREATE INDEX sector_classifications_security_as_of_idx
    ON quantrade.sector_classifications (security_id, as_of_date DESC);

COMMIT;
