# AI Infrastructure Credit Risk Analysis

**Live demo:** [Open the dashboard](https://ai-infrastructure-credit-risk-analysis-sec-filings-vs-market-v.streamlit.app/)
 
AI data center growth is increasingly financed with debt, but the harder credit questions sit with power producers, grid equipment makers, data center REITs and leveraged hardware suppliers, not the big cloud companies. This project checks whether the market's risk pricing for those issuers matches their balance sheets, and flags cases where leverage is rising while the market stays calm.
 
**Data:** SEC EDGAR, FRED, yfinance **Tools:** Python, SQL (SQLite, CTEs and window functions), Streamlit **Scope:** 6 companies, 58 issuer-quarters (started with 11)
 
![Dashboard](Dashboard%201%2C%202.png)
![](Dashboard%203%2C%204.png)
 
---
 
## The Problem
AI data center growth is increasingly financed with debt, but the risk is not where most people look. The big cloud companies can fund capex out of operating cash flow. The harder credit questions sit with power producers, grid equipment makers, data center REITs and leveraged hardware suppliers.
 
- If the market is nervous about a company with sound financials, that is likely hedging.
- If leverage is rising while the market stays calm, that is the case worth flagging early.
---
 
## Key Findings
The sample is small, so these are my reads of the data, not proven results. Full numbers are in `FINDINGS.md`.
 
### 1. The market wasn't pricing debt
- The most leveraged companies were not the most volatile. The link ran the other way (r = -0.41, n = 58).
- Hardware drove most of it (-0.38). Power and data centers showed no real relationship.
- Super Micro had the highest volatility and more cash than debt, so one outlier explains a lot.
### 2. Equinix is the mismatch to watch
- It was the most levered name in every version of the ranking, and its stock was calm (stress 0.3, market risk -0.9).
- That is the pattern the project was built to catch. It is one quarter and one company, so it is a flag, not a prediction.
### 3. My divergence score didn't predict much
- Almost no link to next-quarter returns (-0.14) or volatility changes (0.06).
- Flagged companies returned less (9.1% vs 19.2%), but 14 observations in a strong market isn't enough to lean on.
---
 
## Other Insights
- **Leases didn't matter.** Adding operating lease liabilities left the ranking unchanged, so the leverage story here comes from reported debt.
- **The data gaps were an insight too.** Only 6 of 11 companies had complete SEC data. ETN had no EBITDA tags and GE Vernova had no debt tags, so some of the biggest AI-buildout names are the hardest to monitor with free filings. Each gap is logged in `dq_log`.
## Method
Fundamental stress is the average z-score of lease-adjusted net debt to trailing four-quarter EBITDA, interest coverage and capex efficiency. Market risk is the z-score of 30-day realized volatility. Divergence is stress minus market risk, and an OLS regression estimates how much volatility the fundamentals and the high yield spread would justify.
 
## Technical Problems Solved
- SEC cash flow data is year-to-date, so I subtract consecutive totals to get single quarters.
- A wrong CIK silently returns another company's filings, so each one is checked against the SEC's ticker list. This caught two bad ones (Applied Digital and Super Micro).
- Rows missing debt, operating cash flow or revenue are logged and counted per company instead of dropped silently.
## Limits
There is no free CDS or bond spread data, so equity volatility stands in for market risk. Only 6 of 11 issuers had complete data, quarters overlap, and the sample starts in 2022 in a mostly strong market. Pooling all sectors into one z-score overstates stress for REITs and power producers.
 
## Setup
Set `USER_AGENT` in `get_data.py` to your name and email (the SEC requires it), then run:
```
python get_data.py
python model.py
python findings.py
streamlit run dashboard.py
```

## Acknowledgment

Inspired by a Bloomberg article on AI-related debt and credit risk: https://www.bloomberg.com/news/articles/2026-10-08/ai-debt-spree-hammers-tech-debt-as-traders-rush-to-reprice-risk
