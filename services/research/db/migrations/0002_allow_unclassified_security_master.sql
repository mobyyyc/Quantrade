-- SEC's ticker/exchange association file does not establish common-stock
-- eligibility. Keep those rows as unknown until a later universe gate does.

BEGIN;

ALTER TABLE quantrade.securities
    DROP CONSTRAINT securities_asset_class_check;

ALTER TABLE quantrade.securities
    ADD CONSTRAINT securities_asset_class_check
    CHECK (asset_class IN ('common_stock', 'unknown'));

COMMIT;
