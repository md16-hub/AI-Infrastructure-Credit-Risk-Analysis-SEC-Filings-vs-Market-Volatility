-- This builds the main table of ratios, one row per company per quarter.
-- Anything that gets divided uses NULLIF / COALESCE so a zero or missing number
-- gives a blank (NULL) instead of an error. The model just skips blank rows.
DROP VIEW IF EXISTS v_adjusted;
CREATE VIEW v_adjusted AS
WITH base AS (
    -- adjusted debt = reported debt + operating lease liability, both taken from the
    -- SEC filings. if a company reports no lease liability for a quarter, adjusted
    -- debt is just its reported debt (nothing is estimated). missing cash is treated as 0.
    -- everything is turned into REAL (decimals) because sqlite rounds down when it
    -- divides whole numbers, which made some ratios come out as 0
    SELECT
        f.ticker,
        f.quarter_end_date,
        CAST(f.revenue AS REAL)             AS revenue,
        CAST(f.capex AS REAL)               AS capex,
        CAST(f.ebitda AS REAL)              AS ebitda,
        CAST(f.ebit AS REAL)                AS ebit,
        CAST(f.interest_expense AS REAL)    AS interest_expense,
        CAST(f.operating_cash_flow AS REAL) AS operating_cash_flow,
        COALESCE(CAST(f.cash_and_equivalents AS REAL), 0) AS cash,
        CAST(f.total_debt AS REAL) + COALESCE(CAST(f.operating_lease_liability AS REAL), 0) AS adj_debt
    FROM company_financials f
),
ltm AS (
    -- one quarter of EBITDA is too small (it would make debt look about 4x worse),
    -- so i add up the last 4 quarters. only works if there are 4 quarters of data.
    SELECT
        *,
        CASE WHEN COUNT(ebitda) OVER w = 4 THEN SUM(ebitda) OVER w END AS ebitda_ltm
    FROM base
    WINDOW w AS (PARTITION BY ticker ORDER BY quarter_end_date
                 ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
),
ratios AS (
    SELECT
        ticker,
        quarter_end_date,
        revenue,
        capex,
        -- if EBITDA is negative the ratio doesn't mean anything, so leave it blank
        (adj_debt - cash) / NULLIF(CASE WHEN ebitda_ltm > 0 THEN ebitda_ltm END, 0) AS adj_nd_ebitda,
        -- if there's no interest expense but the company is profitable, coverage is
        -- basically unlimited. i set it to 50, same cap as in model.py
        COALESCE(ebit / NULLIF(interest_expense, 0),
                 CASE WHEN ebit > 0 THEN 50 END)                                    AS interest_coverage,
        capex / NULLIF(revenue, 0)                                                  AS capex_intensity,
        capex / NULLIF(operating_cash_flow, 0)                                      AS capex_to_ocf,
        -- how much more revenue this quarter vs how much capex was spent in the last 4 quarters
        (revenue - LAG(revenue) OVER (PARTITION BY ticker ORDER BY quarter_end_date))
          / NULLIF(SUM(capex) OVER (PARTITION BY ticker ORDER BY quarter_end_date
                                    ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0)   AS capex_eff
    FROM ltm
)
SELECT
    *,
    adj_nd_ebitda
      - LAG(adj_nd_ebitda) OVER (PARTITION BY ticker ORDER BY quarter_end_date) AS leverage_change
FROM ratios;


-- This one gets the rolling 30 day volatility and beta (compared to QQQ).
-- sqlite doesn't have a standard deviation function, so i use
-- variance = average of squares - square of the average, and take the square root in python later.
-- beta = covariance with QQQ / variance of QQQ
DROP VIEW IF EXISTS v_market_metrics;
CREATE VIEW v_market_metrics AS
WITH returns AS (
    SELECT
        ticker,
        date,
        close / NULLIF(LAG(close) OVER (PARTITION BY ticker ORDER BY date), 0) - 1 AS ret
    FROM prices
),
joined AS (
    -- need the stock return and the QQQ return from the same day
    SELECT r.ticker, r.date, r.ret, b.ret AS bench_ret
    FROM returns r
    JOIN returns b ON b.ticker = 'QQQ' AND b.date = r.date
    WHERE r.ret IS NOT NULL AND b.ret IS NOT NULL
),
rolling AS (
    SELECT
        ticker,
        date,
        COUNT(*)                   OVER w AS n,
        AVG(ret)                   OVER w AS mx,
        AVG(ret * ret)             OVER w AS mxx,
        AVG(bench_ret)             OVER w AS my,
        AVG(bench_ret * bench_ret) OVER w AS myy,
        AVG(ret * bench_ret)       OVER w AS mxy
    FROM joined
    WINDOW w AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
SELECT
    ticker,
    date,
    mxx - mx * mx AS var_30d,
    (mxy - mx * my) / NULLIF(myy - my * my, 0) AS beta_30d
FROM rolling
WHERE n = 30;
