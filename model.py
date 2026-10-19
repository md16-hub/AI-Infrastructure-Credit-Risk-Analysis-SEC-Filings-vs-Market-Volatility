import sqlite3
import numpy as np
import pandas as pd
import statsmodels.api as sm

con = sqlite3.connect("credit.db")

fin = pd.read_sql("select * from v_adjusted", con, parse_dates=["quarter_end_date"])
mkt = pd.read_sql("select ticker, date, var_30d, beta_30d from v_market_metrics",
                  con, parse_dates=["date"])
macro = pd.read_sql("select * from macro", con, parse_dates=["date"])
sector = pd.read_sql("select ticker, sector from sectors", con)
fin = fin.merge(sector, on="ticker")

mkt["vol_30d"] = np.sqrt(mkt["var_30d"].clip(lower=0)) * np.sqrt(252)
mkt = mkt[["ticker", "date", "vol_30d", "beta_30d"]]


def one_series(name, new_col):
    """Pulls one FRED series out of the macro table."""
    s = macro[macro.series == name][["date", "value"]]
    return s.rename(columns={"value": new_col})


def attach(left, right, by=None):
    """Matches each quarter end to the most recent market or macro value before it.

    Quarter ends are often weekends or holidays with no price, so matching the exact
    date would lose rows. Using the closest earlier date fixes that and also makes
    sure I'm not using data from after the quarter ended.
    """
    out = pd.merge_asof(left.sort_values("quarter_end_date"), right.sort_values("date"),
                        left_on="quarter_end_date", right_on="date", by=by)
    return out.drop(columns="date")


def z(s):
    """Z-score: how many standard deviations a number is from the average.

    This puts different ratios on the same scale so I can average them into one score.
    """
    return (s - s.mean()) / s.std(ddof=0)


panel = attach(fin, mkt, by="ticker")
panel = attach(panel, one_series("BAMLH0A0HYM2", "hy_spread"))
panel = attach(panel, one_series("BAMLC0A4CBBB", "bbb_spread"))

panel = panel.replace([np.inf, -np.inf], np.nan)
panel["interest_coverage"] = panel["interest_coverage"].clip(-50, 50)  # cap the really extreme values

needed = ["adj_nd_ebitda", "interest_coverage", "capex_eff", "vol_30d", "hy_spread"]
before = set(panel.ticker)
panel = panel.dropna(subset=needed).copy()
print("rows used:", len(panel), "| tickers dropped for missing data:", before - set(panel.ticker))

# regression to see how risky the market "should" think each company is, based on its
# numbers and the overall credit spread. i use volatility as the market risk because
# i can't get free bond spreads for each company
X = sm.add_constant(panel[["adj_nd_ebitda", "interest_coverage", "capex_eff", "hy_spread"]])
ols = sm.OLS(panel["vol_30d"], X).fit()
print(ols.summary())
panel["fair_vol"] = ols.predict(X)
panel["residual"] = panel["vol_30d"] - panel["fair_vol"]

# coverage and capex efficiency are flipped (minus sign) so a higher z always means more stress
panel["z_leverage"] = z(panel["adj_nd_ebitda"])
panel["z_coverage"] = z(-panel["interest_coverage"])
panel["z_capex_eff"] = z(-panel["capex_eff"])
panel["z_fund"] = z(panel[["z_leverage", "z_coverage", "z_capex_eff"]].mean(axis=1))
panel["z_market"] = z(panel["vol_30d"])
panel["divergence"] = panel["z_fund"] - panel["z_market"]

panel["label"] = np.select(
    [(panel["z_market"] > 1) & (panel["z_fund"] < 0.5),
     panel["divergence"] > 1],
    ["Hedging noise outlier", "Review: fundamentals ahead of market"],
    default="In line",
)
panel["exec_risk"] = (panel["z_capex_eff"] > 1).astype(int)

cols = ["ticker", "sector", "quarter_end_date", "capex", "adj_nd_ebitda", "interest_coverage",
        "capex_intensity", "capex_eff", "vol_30d", "beta_30d", "hy_spread", "bbb_spread",
        "fair_vol", "residual", "z_leverage", "z_coverage", "z_capex_eff",
        "z_fund", "z_market", "divergence", "label", "exec_risk"]
panel[cols].to_sql("scores", con, if_exists="replace", index=False)
con.commit()
con.close()

latest = panel.sort_values("quarter_end_date").groupby("ticker").tail(1)
print("\nlatest quarter per company:")
print(latest.sort_values("divergence", ascending=False)[
    ["ticker", "z_fund", "z_market", "divergence", "label", "exec_risk"]].round(2).to_string(index=False))
