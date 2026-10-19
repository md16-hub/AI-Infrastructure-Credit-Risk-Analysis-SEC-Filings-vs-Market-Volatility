# AI Buildout Credit Stress Monitor

## Acknowledgment & Inspiration

Inspired by an article from Bloomberg Intelligence on rising AI-related debt and credit risk, I developed this project to monitor leverage and credit market risk across the AI infrastructure supply chain.

Source: https://www.bloomberg.com/news/articles/2026-10-08/ai-debt-spree-hammers-tech-debt-as-traders-rush-to-reprice-risk

## The question

AI data center growth is increasingly financed with debt, but the risk is not where most people look. The big cloud companies can fund capex out of operating cash flow. The harder credit questions sit with the power producers, grid equipment makers, data center REITs, and leveraged hardware suppliers that face grid bottlenecks, construction delays, and heavy leverage. This project asks whether the market's risk pricing for those issuers matches what their balance sheets show. If the market is nervous about a company with sound financials, that is likely hedging. If leverage is rising while the market stays calm, that is the case worth flagging early.

## Universe

11 issuers across three groups: power and grid infrastructure (Constellation Energy, Vistra, Eaton, GE Vernova), data center REITs and operators (Equinix, Digital Realty, Applied Digital), and high-leverage hardware (Oracle, Super Micro, Seagate, Western Digital). Only 6 had complete data for scoring. The full list is in get_data.py.

## Data and method

Quarterly financials come from SEC EDGAR filings, the credit backdrop (BBB and high yield option-adjusted spreads, 10-year yield) from FRED, and daily prices from yfinance. Everything is loaded into SQLite and transformed with SQL using CTEs and window functions.

Fundamental stress is the average z-score of lease-adjusted net debt to trailing four-quarter EBITDA, interest coverage, and capex efficiency. Debt is adjusted using the operating lease liability reported in each filing, not an estimate. Market risk is the z-score of 30-day realized volatility. Divergence is fundamental stress minus market risk, and an OLS regression estimates how much volatility the fundamentals and the high yield spread would justify.

## Findings

The sample is small, so these are exploratory. Full output with sample sizes is in FINDINGS.md.

- **Market risk did not follow balance sheet stress.** The correlation was -0.41 (n=58), so the weaker balance sheets were often the calmer stocks. By sector it was -0.38 for hardware (n=30), -0.07 for power (n=18), and 0.09 for data centers (n=10). Super Micro likely drives this: it had the highest volatility in the sample with below-average leverage.
- **Lease liabilities did not change the leverage ranking.** Equinix stayed the most levered, then Vistra, Constellation, Western Digital, Seagate, and Super Micro. Constellation and Vistra had no operating lease liability in the filings I parsed, so the check is partial for them.
- **The divergence score did not predict much.** It correlated at -0.14 with next-quarter returns (n=52) and 0.06 with the change in volatility. Flagged companies averaged a 9.1% next-quarter return (n=14) against 19.2% for the rest (n=38). I did not test significance, and the quarters overlap.
- **Equinix was the latest-quarter flag.** Its balance sheet looked more stressed than its volatility implied. Super Micro and Seagate showed the opposite and were labeled hedging noise.
- **Data coverage was a finding too.** ETN had no EBIT or EBITDA tags, and GE Vernova had no debt, interest expense, or EBITDA tags. The pipeline logs these rows to a `dq_log` table instead of dropping them silently.

## What it produces

A Streamlit dashboard with four views: an issuer stress heatmap, a divergence matrix plotting fundamental stress against market risk, a chart of total capex against credit spreads by calendar quarter, and a watchlist of flagged companies. A separate script, findings.py, writes FINDINGS.md.

## Technical problems solved

- SEC cash flow data is year-to-date, so consecutive totals are subtracted to get single quarters.
- Leverage uses trailing four-quarter EBITDA, since one quarter overstates it about four times.
- SQLite integer division rounded small ratios to zero, so columns are cast to decimals.
- A wrong CIK silently returns another company's filings, so each one is checked against the SEC's ticker list. This caught two bad ones (Applied Digital and Super Micro).
- Fiscal year ends differ by company, so capex is grouped by calendar quarter.
- Rows missing debt, operating cash flow, or revenue are logged to `dq_log` and counted per company.

## Setup

```
pip install pandas statsmodels requests yfinance plotly streamlit
```

Set USER_AGENT in get_data.py to your name and email (the SEC requires it), then run:

```
python get_data.py
python model.py
python findings.py
streamlit run dashboard.py
```

## Limitations

- There is no free CDS or issuer-level bond spread data, so equity volatility stands in for market risk and the hedging label is inferred.
- Only 6 of 11 issuers had complete data, and the quarters overlap, so the results are not independent observations.
- The sample starts in 2022 and is mostly a strong equity market.
- Lease adjustment uses only filed operating lease liabilities, and EBITDA is not adjusted for lease cost, so leverage runs slightly high for heavy lessors.
- Pooling all sectors into one z-score overstates stress for REITs and power producers.
- GE Vernova has a short history since its 2024 spin-off, so spot-check its values against the filings.
