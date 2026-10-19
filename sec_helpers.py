import time
import requests
import pandas as pd

# companies don't all use the same name for the same number, so for each thing
# i want (revenue, capex, etc) i try a few names in order
TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "ebit": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt",
                         "InterestExpenseNonoperating", "InterestAndDebtExpense"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements", "PaymentsToDevelopRealEstateAssets"],
    "total_debt": ["LongTermDebt", "DebtLongtermAndShorttermCombinedAmount"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    # operating lease liability as reported on the balance sheet (real filing data,
    # used to adjust debt for leases instead of a guessed multiplier)
    "operating_lease_liability": ["OperatingLeaseLiability"],
}


def get_json(url, headers, retries=3):
    """Gets json from the SEC website.

    The SEC only allows about 10 requests per second and will block you if you go
    faster, so this waits a bit before every request. If it still says "slow down"
    (error 429 or 503) it waits longer and tries again.
    """
    for attempt in range(retries):
        time.sleep(0.1)
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code in (429, 503):
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"SEC kept telling us to slow down on {url}")


def entries_for(facts, tag):
    """Gets every number a company reported under one name (tag), only from 10-Qs and 10-Ks.

    If the company never used that name it just returns an empty table instead of
    crashing, so the code can move on and try the next name in the list.
    """
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return pd.DataFrame()
    df = pd.DataFrame(node["units"].get("USD", []))
    if df.empty:
        return df
    df = df[df["form"].isin(["10-Q", "10-K"])].copy()
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    if "start" in df.columns:
        df["start"] = pd.to_datetime(df["start"])
    return df


def flow_quarterly(df):
    """Turns running totals into single quarters.

    Things like capex and cash flow are reported as "year to date" in the 10-Qs
    (3 months, then 6 months, then 9 months) and the 10-K gives the whole year.
    To get one quarter I subtract the last running total from the new one.
    The same number sometimes gets filed again later, so I keep the newest one.
    """
    if df.empty or "start" not in df.columns:
        return pd.Series(dtype=float)
    df = df.dropna(subset=["start"])
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")
    out = {}
    for start, g in df.groupby("start"):
        g = g.sort_values("end")
        prev_end, prev_val = start, 0.0
        for _, r in g.iterrows():
            gap = (r["end"] - prev_end).days
            if 75 <= gap <= 105:   # a quarter is about 90 days, some years are a few days off
                out.setdefault(r["end"], r["val"] - prev_val)
            prev_end, prev_val = r["end"], r["val"]
    return pd.Series(out, dtype=float).sort_index()


def stock_series(df):
    """Balance sheet numbers (debt, cash) are just the amount on one day, so I only keep the newest filing for each date."""
    if df.empty:
        return pd.Series(dtype=float)
    df = df.sort_values("filed").drop_duplicates("end", keep="last")
    return df.set_index("end")["val"].sort_index()


def combine(series_list):
    """Merges the results from the different names. The first name is used when it has a number, and the later names only fill in the blanks."""
    series_list = [s for s in series_list if len(s) > 0]
    if not series_list:
        return pd.Series(dtype=float)
    out = series_list[0]
    for s in series_list[1:]:
        out = out.combine_first(s)
    return out.sort_index()


def build_company(facts):
    """Makes one table for a company with one row per quarter.

    If none of the names work for something, that column just ends up empty
    instead of crashing. get_data.py prints a warning so I know which one is missing.
    """
    def flow(name):
        return combine([flow_quarterly(entries_for(facts, t)) for t in TAGS[name]])

    def stock(name):
        return combine([stock_series(entries_for(facts, t)) for t in TAGS[name]])

    # a lot of companies don't report total debt in one number, only the pieces,
    # so if the total is missing i add the long term part and the current part
    debt = stock("total_debt")
    noncur = stock_series(entries_for(facts, "LongTermDebtNoncurrent"))
    cur = stock_series(entries_for(facts, "LongTermDebtCurrent"))
    if len(noncur) > 0:
        debt = debt.combine_first(noncur.add(cur, fill_value=0))

    # same idea for leases: if there is no total, add the long term and current pieces
    lease = stock("operating_lease_liability")
    lease_noncur = stock_series(entries_for(facts, "OperatingLeaseLiabilityNoncurrent"))
    lease_cur = stock_series(entries_for(facts, "OperatingLeaseLiabilityCurrent"))
    if len(lease_noncur) > 0:
        lease = lease.combine_first(lease_noncur.add(lease_cur, fill_value=0))

    d = pd.DataFrame({
        "revenue": flow("revenue"),
        "ebit": flow("ebit"),
        "interest_expense": flow("interest_expense").abs(),
        "da": flow("da"),
        "operating_cash_flow": flow("operating_cash_flow"),
        "capex": flow("capex").abs(),
        "total_debt": debt,
        "cash_and_equivalents": stock("cash"),
        "operating_lease_liability": lease,
    })
    d["ebitda"] = d["ebit"] + d["da"]
    return d.dropna(subset=["revenue"])


def filing_info(facts):
    """Finds the fiscal year, quarter label and filing date for each period end.

    The same number shows up again as a comparison in later filings, so for every
    period end I keep the earliest filing, which is the report that first
    announced it. The 10-K covers the full year, so it gets labeled Q4.
    """
    frames = []
    for tags in TAGS.values():
        for t in tags:
            df = entries_for(facts, t)
            if not df.empty and {"fy", "fp"} <= set(df.columns):
                frames.append(df[["end", "filed", "fy", "fp"]])
    if not frames:
        return pd.DataFrame(columns=["fiscal_year", "quarter", "filed_date"])
    info = pd.concat(frames).sort_values("filed").drop_duplicates("end", keep="first").set_index("end")
    info["quarter"] = info["fp"].replace({"FY": "Q4"})
    info["filed_date"] = info["filed"].dt.strftime("%Y-%m-%d")
    return info.rename(columns={"fy": "fiscal_year"})[["fiscal_year", "quarter", "filed_date"]]
