# AI Buildout Credit Stress Monitor

# AI Infrastructure Credit Risk Analysis

**Live demo:** [Open the dashboard](https://ai-infrastructure-credit-risk-analysis-sec-filings-vs-market-v.streamlit.app/)

![Dashboard](<docs/Dashboard 1, 2.png>)
![](<docs/Dashboard 3, 4.png>)

## The question

AI data center growth is increasingly financed with debt, but the risk is not where most people look. The big cloud companies can fund capex out of operating cash flow. The harder credit questions sit with the power producers, grid equipment makers, data center REITs, and leveraged hardware suppliers. This project asks whether the market's risk pricing for those issuers matches what their balance sheets show. If the market is nervous about a company with sound financials, that is likely hedging. If leverage is rising while the market stays calm, that is the case worth flagging early.

## What I took from it

The sample is small (6 companies, 58 issuer-quarters), so this is my read of the data, not a proven result. The full numbers are in FINDINGS.md.

**The market wasn't pricing debt.** I expected the most leveraged companies to be the most volatile. It went the other way (r = -0.41, n=58): the weakest balance sheets were often the calmest stocks. Hardware drove most of it (-0.38), while power and data centers showed no real relationship.

**One stock explains a lot of it.** Super Micro had the highest volatility in the sample and more cash than debt. That tells me its volatility comes from something the balance sheet can't show, like accounting questions or AI hype. I haven't tested that, but it's why I'd treat the correlation as one outlier, not a rule.

**The mismatch I'd watch is Equinix.** It was the most levered name in every version of the ranking, and its stock was calm (stress 0.3, market risk -0.9). That's the pattern the project was built to catch: leverage up, market quiet. It's one quarter and one company, so it's a flag to look at, not a prediction.

**Leases didn't matter here.** Adding operating lease liabilities left the ranking unchanged. I expected it to shuffle the order, so this told me the leverage story in this group comes from reported debt.

**My divergence score didn't predict much.** It had almost no link to next-quarter returns (-0.14) or volatility changes (0.06). Flagged companies did return less (9.1% vs 19.2%), but 14 observations in a strong market isn't enough to lean on.

**The data gaps were an insight too.** Only 6 of 11 companies had complete SEC data. ETN had no EBITDA tags and GE Vernova had no debt tags, so some of the biggest AI-buildout names are the hardest to monitor with free filings. Each gap is logged in `dq_log`.

## Data and method

I started with 11 issuers across power and grid (Constellation, Vistra, Eaton, GE Vernova), data centers (Equinix, Digital Realty, Applied Digital), and hardware (Oracle, Super Micro, Seagate, Western Digital). Quarterly financials come from SEC EDGAR, credit spreads and the 10-year yield from FRED, and daily prices from yfinance. Everything is loaded into SQLite and transformed with SQL using CTEs and window functions.

Fundamental stress is the average z-score of lease-adjusted net debt to trailing four-quarter EBITDA, interest coverage, and capex efficiency. Market risk is the z-score of 30-day realized volatility. Divergence is fundamental stress minus market risk, and an OLS regression estimates how much volatility the fundamentals and the high yield spread would justify.

## Technical problems solved

- SEC cash flow data is year-to-date, so consecutive totals are subtracted to get single quarters.
- Leverage uses trailing four-quarter EBITDA, since one quarter overstates it about four times.
- A wrong CIK silently returns another company's filings, so each one is checked against the SEC's ticker list. This caught two bad ones (Applied Digital and Super Micro).
- Rows missing debt, operating cash flow, or revenue are logged to `dq_log` and counted per company instead of dropped silently.

## Setup

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


## Acknowledgment

Inspired by a Bloomberg article on AI-related debt and credit risk: https://www.bloomberg.com/news/articles/2026-10-08/ai-debt-spree-hammers-tech-debt-as-traders-rush-to-reprice-risk
