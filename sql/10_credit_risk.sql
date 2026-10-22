-- Credit risk, Standardised Approach (CRR Part Three, Title II, Chapter 2).
-- Inputs (registered by corep/pipeline.py): exposures, off_balance, dt_exposure_class,
-- dt_risk_weight, dt_other_items, dt_ccf, params.

-- 1. Exposure class: first matching rule of the decision table, in priority order.
CREATE OR REPLACE TABLE classified AS
WITH candidates AS (
    SELECT e.*, d.priority, d.exposure_class, d.c02_row, d.crr_article, d.note
    FROM exposures e
    JOIN dt_exposure_class d
      ON (d.counterparty_type = '*' OR d.counterparty_type = coalesce(e.counterparty_type, ''))
     AND (d.product = '*' OR d.product = e.product)
     AND (d.default_flag = '*' OR d.default_flag = CAST(e.default_flag AS VARCHAR))
     AND (d.has_property_value = '*' OR d.has_property_value = CASE WHEN e.property_value IS NULL THEN '0' ELSE '1' END)
)
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (PARTITION BY exposure_id ORDER BY priority) AS rn FROM candidates
) WHERE rn = 1;

-- 2. Exposure value (Art 111(1)): accounting value net of specific credit risk adjustments.
--    Residential mortgages are split (Art 125(1)): the part up to 55% of the property value at 20%,
--    the remainder at the risk weight of the unsecured counterparty (retail, 75%).
CREATE OR REPLACE TABLE credit_rwa AS
WITH base AS (
    SELECT c.*,
           gross_amount - specific_provision AS exposure_value,
           CASE WHEN original_maturity_days IS NOT NULL AND original_maturity_days <= 90 THEN '1' ELSE '0' END AS short_term
    FROM classified c
), parts AS (
    -- one row per exposure, except mortgages that become a secured and an unsecured part
    SELECT *, '0151' AS part_row, least(exposure_value, 0.55 * property_value) AS part_value
    FROM base WHERE exposure_class = 'mortgage'
    UNION ALL
    SELECT *, '0152', exposure_value - least(exposure_value, 0.55 * property_value)
    FROM base WHERE exposure_class = 'mortgage'
    UNION ALL
    SELECT *, c02_row, exposure_value FROM base WHERE exposure_class <> 'mortgage'
)
SELECT p.exposure_id, p.gl_account, p.counterparty_type, p.product, p.exposure_class, p.c02_row,
       p.part_row, p.cqs, p.short_term, p.default_flag, p.gross_amount, p.specific_provision,
       p.part_value AS exposure_value,
       CASE
         WHEN p.exposure_class = 'mortgage' AND p.part_row = '0151' THEN 0.20
         WHEN p.exposure_class = 'mortgage' THEN 0.75
         WHEN p.exposure_class = 'default' AND p.product = 'residential_mortgage' THEN 1.00          -- Art 127(2)
         WHEN p.exposure_class = 'default'
              THEN CASE WHEN p.specific_provision >= 0.20 * p.gross_amount THEN 1.00 ELSE 1.50 END -- Art 127(1)
         WHEN p.exposure_class = 'central_government' AND (SELECT eu_sovereign_domestic_zero FROM params)
              AND p.currency = 'EUR' AND p.country IN (SELECT country FROM eu_member_states) THEN 0.00 -- Art 114(4)
         WHEN p.exposure_class = 'other_items' THEN o.risk_weight
         ELSE w.risk_weight
       END AS risk_weight,
       CASE
         WHEN p.exposure_class = 'central_government' AND (SELECT eu_sovereign_domestic_zero FROM params)
              AND p.currency = 'EUR' AND p.country IN (SELECT country FROM eu_member_states) THEN 'Art 114(4)'
         WHEN p.exposure_class IN ('mortgage') THEN 'Art 125(1)'
         WHEN p.exposure_class = 'default' THEN 'Art 127'
         WHEN p.exposure_class = 'other_items' THEN o.crr_article
         ELSE w.crr_article
       END AS rw_basis
FROM parts p
LEFT JOIN dt_risk_weight w
       ON w.exposure_class = p.exposure_class
      AND (w.cqs = '*' OR w.cqs = coalesce(p.cqs, ''))
      AND (w.short_term = '*' OR w.short_term = p.short_term)
LEFT JOIN dt_other_items o ON o.product = p.product;

-- 3. Off-balance sheet items (Art 111(2), Annex I): exposure value = nominal x CCF,
--    risk-weighted as the counterparty (unrated corporates 100%, retail 75%).
CREATE OR REPLACE TABLE off_balance_rwa AS
SELECT o.commitment_id, o.product, o.counterparty_type, o.nominal_amount, c.sa_ccf, c.lr_ccf, c.c47_row,
       o.nominal_amount * c.sa_ccf AS exposure_value,
       CASE WHEN o.counterparty_type = 'retail' THEN 0.75 ELSE coalesce(w.risk_weight, 1.00) END AS risk_weight,
       CASE WHEN o.counterparty_type = 'retail' THEN '0140' ELSE '0125' END AS c02_row
FROM off_balance o
JOIN dt_ccf c USING (product)
LEFT JOIN dt_risk_weight w ON w.exposure_class = 'corporate' AND w.cqs = coalesce(o.cqs, '') AND w.short_term = '*';

-- 4. RWEA per C 02.00 row.
CREATE OR REPLACE TABLE c02_credit AS
SELECT row, sum(rwea) AS rwea FROM (
    SELECT part_row AS row, exposure_value * risk_weight AS rwea FROM credit_rwa
    UNION ALL
    SELECT c02_row, exposure_value * risk_weight FROM off_balance_rwa
) GROUP BY row;
