import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="AI Credit Stress Monitor", layout="wide")
st.markdown("<style>html, body, .stApp, h1, h2, h3, p, label, [data-testid='stMetricValue'], "
            "[data-testid='stMetricLabel'] {font-family: Arial, Helvetica, sans-serif;}</style>",
            unsafe_allow_html=True)

COLORS = {"Power": "#4C78A8", "Data center": "#F58518", "Hardware": "#54A24B"}


def show(fig, height=450):
    fig.update_layout(font_family="Arial", height=height, legend=dict(orientation="h", y=-0.25, title=None))
    st.plotly_chart(fig, use_container_width=True)


st.title("AI Buildout Credit Stress Monitor")
st.caption("Is the market pricing in the real credit risk, or is it just hedging noise?")

con = sqlite3.connect("credit.db")
scores = pd.read_sql("select * from scores", con, parse_dates=["quarter_end_date"])
macro = pd.read_sql("select * from macro", con, parse_dates=["date"])

tickers = sorted(scores["ticker"].unique())
picked = st.sidebar.multiselect("Tickers", tickers, default=tickers)
if not picked:
    st.warning("Pick at least one ticker in the sidebar.")
    st.stop()
# latest quarter per company
latest = (scores[scores.ticker.isin(picked)]
          .sort_values("quarter_end_date").groupby("ticker").tail(1))
st.caption(f"{len(scores)} issuer-quarters across {len(tickers)} companies. Small sample, so exploratory.")

a, b, c = st.columns(3)
a.metric("Companies", len(latest))
b.metric("Review flags", int((latest.label == "Review: fundamentals ahead of market").sum()))
c.metric("Execution risk flags", int(latest.exec_risk.sum()))

left, right = st.columns(2)
with left:
    st.subheader("Fundamental stress by company")
    fig = px.bar(latest.sort_values("z_fund", ascending=False), x="ticker", y="z_fund", color="sector",
                 text="ticker", color_discrete_map=COLORS,
                 labels={"z_fund": "Fundamental stress (z)", "ticker": ""})
    fig.update_traces(textposition="outside")
    show(fig)
    st.caption("Higher = weaker balance sheet compared to the other companies.")
with right:
    st.subheader("Fundamental stress vs market risk")
    fig = px.scatter(latest, x="z_fund", y="z_market", text="ticker", color="sector", symbol="label",
                     color_discrete_map=COLORS,
                     labels={"z_fund": "Fundamental stress (z)", "z_market": "Market risk (z)"})
    fig.update_traces(marker_size=12)
    # alternate label positions so close points (VST and CEG) don't overprint
    fig.for_each_trace(lambda t: t.update(
        textposition=["top center" if i % 2 == 0 else "bottom center" for i in range(len(t.x))]))
    fig.add_hline(y=0, line_dash="dash").add_vline(x=0, line_dash="dash")
    show(fig)
    st.caption("Color = sector, shape = flag label. Top left = market scared but fundamentals ok "
               "(hedging noise?). Bottom right = fundamentals worse but market calm.")

st.subheader("AI capex vs credit spreads")
# companies have different fiscal years, so i group capex by calendar quarter
scores["cal_q"] = scores["quarter_end_date"].dt.to_period("Q").dt.end_time.dt.normalize()
capex = scores.groupby("cal_q")["capex"].sum().div(1e9).rename("capex_billions").reset_index()
spreads = (macro[macro.series.isin(["BAMLH0A0HYM2", "BAMLC0A4CBBB"])]
           .pivot(index="date", columns="series", values="value")
           .resample("QE").mean().reset_index())
c1, c2 = st.columns(2)
with c1:
    show(px.bar(capex, x="cal_q", y="capex_billions", labels={"capex_billions": "Total capex ($B)"}), 350)
with c2:
    show(px.line(spreads, x="date", y=["BAMLH0A0HYM2", "BAMLC0A4CBBB"],
                 labels={"value": "Spread (%)", "variable": ""}), 350)
st.caption("BAMLH0A0HYM2 = high yield spread, BAMLC0A4CBBB = BBB spread.")

st.subheader("Companies to look at")
flagged = latest[(latest.label != "In line") | (latest.exec_risk == 1)]
st.dataframe(flagged[["ticker", "sector", "label", "exec_risk", "adj_nd_ebitda", "interest_coverage",
                      "capex_eff", "z_fund", "z_market", "divergence"]].round(2), hide_index=True)

