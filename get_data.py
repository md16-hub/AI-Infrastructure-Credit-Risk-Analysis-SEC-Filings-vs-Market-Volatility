import sqlite3
import pandas as pd
import yfinance as yf

from sec_helpers import get_json, build_company, filing_info
from exports import export_csvs

DB = "credit.db"
START = "2022-01-01"

# the SEC wants your name and email in every request. put yours in before running
USER_AGENT = "Mim Datta dattamim876@gmail.com"

ciks = {
    "CEG": 1868275, "VST": 1692819, "ETN": 1551182, "GEV": 1996810,
    "EQIX": 1101239, "DLR": 1297996, "APLD": 1844852,
    "ORCL": 1341439, "SMCI": 1375151, "STX": 1137789, "WDC": 106040,
}
sector = {"CEG": "Power", "VST": "Power", "ETN": "Power", "GEV": "Power",
          "EQIX": "Data center", "DLR": "Data center", "APLD": "Data center",
          "ORCL": "Hardware", "SMCI": "Hardware", "STX": "Hardware", "WDC": "Hardware"}

tickers = list(ciks)
benchmarks = ["QQQ", "LQD", "HYG"]
fred_series = ["DGS10", "BAMLH0A0HYM2", "BAMLC0A4CBBB"]

if "name@university.edu" in USER_AGENT:
    raise SystemExit("Set USER_AGENT to your real name and email first (SEC requirement).")
headers = {"User-Agent": USER_AGENT}


def get_fred(series_id):
    """Downloads one FRED series as a csv.

    This link doesn't need an API key and it's the same data as the download
    button on the FRED page. FRED puts a "." on days with no data, which breaks the
    number column, so those get turned into blanks and dropped.
    """
    start_str = pd.to_datetime(START).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_str}"
    df = pd.read_csv(url)
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["series"] = series_id
    return df.dropna()


def check_ciks():
    """Checks my CIK numbers against the SEC's own list.

    A wrong CIK doesn't give an error, it just pulls a different company's
    filings, so I check first. If one is different it uses the SEC's number.
    """
    listing = get_json("https://www.sec.gov/files/company_tickers.json", headers)
    official = {v["ticker"]: int(v["cik_str"]) for v in listing.values()}
    for tk in tickers:
        real = official.get(tk)
        if real is not None and real != ciks[tk]:
            print(f"{tk}: CIK {ciks[tk]} does not match SEC ({real}), using SEC's")
            ciks[tk] = real


# macro series from FRED (10-year yield, high yield spread, BBB spread)
macro = pd.concat([get_fred(s) for s in fred_series])
macro["date"] = pd.to_datetime(macro["date"]).dt.strftime("%Y-%m-%d")

# daily prices for the companies plus the benchmarks
px = yf.download(tickers + benchmarks, start=START, auto_adjust=True, progress=False)["Close"]
px.index = pd.to_datetime(px.index).strftime("%Y-%m-%d")
px.index.name = "date"
prices = px.reset_index().melt(id_vars="date", var_name="ticker", value_name="close").dropna()

check_ciks()

rows = []
for tk in tickers:
    try:
        facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[tk]:010d}.json", headers)
    except Exception as err:
        print(tk, "failed:", err)
        continue
    print(tk, "->", facts.get("entityName"))
    d = build_company(facts).join(filing_info(facts))
    d = d[pd.to_datetime(d.index) >= pd.to_datetime(START)]
    empty_cols = [c for c in d.columns if d[c].isna().all()]
    if empty_cols:
        print("   couldn't find:", ", ".join(empty_cols))
    d["ticker"] = tk
    # the index isn't always a datetime index after the join, so convert it first
    d["quarter_end_date"] = pd.to_datetime(d.index).strftime("%Y-%m-%d")
    rows.append(d.reset_index(drop=True))

# errors="ignore" so the script doesn't crash if a company has no "da" column at all
financials = pd.concat(rows).drop(columns=["da"], errors="ignore")

# log every row dropped for missing required fields instead of dropping silently
required = ["total_debt", "operating_cash_flow", "revenue"]
dq_rows = []
for col in required:
    missing = financials[financials[col].isna()]
    for _, r in missing.iterrows():
        dq_rows.append({
            "ticker": r["ticker"],
            "quarter_end_date": r["quarter_end_date"],
            "rule": "missing_required_field",
            "detail": col,
        })
dq_log = pd.DataFrame(dq_rows, columns=["ticker", "quarter_end_date", "rule", "detail"])

# count rows per company before and after the drop so nothing disappears quietly
before = financials.groupby("ticker").size()
financials = financials.dropna(subset=required)
after = financials.groupby("ticker").size()

lost = before.sub(after, fill_value=0).astype(int)
lost = lost[lost > 0]
if not lost.empty:
    print("\nrows dropped for missing required fields:")
    print(lost.to_string())
gone = [t for t in tickers if t not in after.index]
if gone:
    print("WARNING: no rows left for:", ", ".join(gone))

financials["fiscal_year"] = financials["fiscal_year"].astype("Int64")

sectors = pd.DataFrame({"ticker": tickers})
sectors["sector"] = sectors["ticker"].map(sector)

con = sqlite3.connect(DB)
macro.to_sql("macro", con, if_exists="replace", index=False)
prices.to_sql("prices", con, if_exists="replace", index=False)
financials.to_sql("company_financials", con, if_exists="replace", index=False)
sectors.to_sql("sectors", con, if_exists="replace", index=False)
dq_log.to_sql("dq_log", con, if_exists="replace", index=False)
con.execute("DROP TABLE IF EXISTS lease_adj")  # old table from the guessed multiplier, no longer used
con.executescript(open("queries.sql").read())
con.commit()
export_csvs(con, macro, financials)
con.close()


print("\nquarters per company:")
print(financials.groupby("ticker").size().to_string())