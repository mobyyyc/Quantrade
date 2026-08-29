-- Complete corporate-action records are evidence: duplicates are no-ops and
-- prior rows cannot be revised or removed in place.

BEGIN;

CREATE TRIGGER corporate_actions_immutable
BEFORE UPDATE OR DELETE ON quantrade.corporate_actions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();

COMMIT;
