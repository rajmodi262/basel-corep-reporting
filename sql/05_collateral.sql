-- CR-001: property valuations from the collateral system (data/property_valuations_2025Q4.csv).
-- A valuation is usable only if it is no older than three years at the reference date
-- (CRR Art 208(3)(a): residential property value monitored at least once every three years).
-- Unusable valuations are kept in `stale_valuations` and reported by DQ-09, never silently applied.

CREATE OR REPLACE TABLE usable_valuations AS
SELECT v.*
FROM property_valuations v, params p
WHERE CAST(v.valuation_date AS DATE) >= CAST(p.reporting_date AS DATE) - INTERVAL 3 YEAR;

CREATE OR REPLACE TABLE stale_valuations AS
SELECT v.* FROM property_valuations v
WHERE v.exposure_id NOT IN (SELECT exposure_id FROM usable_valuations);

CREATE OR REPLACE TABLE exposures_enriched AS
SELECT e.* REPLACE (coalesce(e.property_value, u.valuation_amount) AS property_value),
       CASE WHEN e.property_value IS NULL AND u.valuation_amount IS NOT NULL
            THEN 'collateral feed ' || u.valuation_date END AS valuation_source
FROM exposures e
LEFT JOIN usable_valuations u USING (exposure_id);
