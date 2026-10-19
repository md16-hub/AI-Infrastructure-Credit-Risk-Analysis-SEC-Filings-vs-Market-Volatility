import os
import numpy as np
import pandas as pd


def export_csvs(con, macro, financials, folder="data"):
    """Saves the data as csv files so it can be opened in Excel and checked by hand.

    macro_credit_spreads.csv  daily BBB spread, high yield spread and 10 year yield
    company_financials.csv    one row per company per quarter from SEC filings
    stock_volatility.csv      daily 30 day volatility and beta from the SQL view

    long_term_debt is the debt total used in the model, so it includes the part
    due within a year. The last four columns of company_financials.csv
    (quarter_end_date, revenue, ebit, operating_lease_liability) are extras that the
    model needs.
    """
    os.makedirs(folder, exist_ok=True)

    wide = macro.pivot(index="date", columns="series", values="value")
    wide = wide.rename(columns={"BAMLC0A4CBBB": "bbb_spread", "BAMLH0A0HYM2": "hy_spread",
                                "DGS10": "us10y"})
    wide = wide[["bbb_spread", "hy_spread", "us10y"]].dropna()
    wide = wide.reset_index().rename(columns={"date": "DATE"})
    wide.to_csv(f"{folder}/macro_credit_spreads.csv", index=False)

    cols = ["ticker", "fiscal_year", "quarter", "filed_date", "long_term_debt",
            "cash_and_equivalents", "ebitda", "capex", "operating_cash_flow",
            "interest_expense", "quarter_end_date", "revenue", "ebit",
            "operating_lease_liability"]
    fin = financials.rename(columns={"total_debt": "long_term_debt"}).reindex(columns=cols)
    fin = fin.sort_values(["ticker", "quarter_end_date"])
    fin.to_csv(f"{folder}/company_financials.csv", index=False)

    vol = pd.read_sql("select ticker, date, var_30d, beta_30d from v_market_metrics", con)
    vol["vol_30d"] = np.sqrt(vol["var_30d"].clip(lower=0)) * np.sqrt(252)
    vol[["date", "ticker", "vol_30d", "beta_30d"]].to_csv(f"{folder}/stock_volatility.csv", index=False)
