import streamlit as st
st.set_page_config(page_title="Cohort Retention", layout="wide")

import pandas as pd, re
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ─────────── Helper (only for table bars) ───────────
def bar(p, w=10): return "🟥"*int(round(p/10)) + "⬜"*(w-int(round(p/10)))

# ─────────── Load data ───────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load(p): return pd.read_csv(p, sep="\t")

df_raw = load(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ─────────── UI filters ───────────
min_d, max_d = df_raw["created_at"].dt.date.agg(["min", "max"])
start, end   = st.date_input("Date range", [min_d, max_d], min_d, max_d)
weekly       = st.checkbox("Weekly cohorts", False)

utm_col, price_col = "user_visit.utm_source", "price.price_option_text"
sel_utm   = st.multiselect("UTM source",
                           sorted(df_raw[utm_col].dropna().unique()),
                           default=sorted(df_raw[utm_col].dropna().unique()))
sel_price = st.multiselect("Price option",
                           sorted(df_raw[price_col].dropna().unique()),
                           default=sorted(df_raw[price_col].dropna().unique()))

# cohorts for LTV-lines
cohort_opts = [str(d) for d in sorted(df_raw["created_at"].dt.date.unique(), reverse=True)]
sel_cohorts = st.multiselect("Cohorts to plot (LTV-lines)",
                             cohort_opts[:10], default=cohort_opts[:5])

# ─────────── Filter data ───────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end)) &
    (df_raw[utm_col].isin(sel_utm)) &
    (df_raw[price_col].isin(sel_price))
].copy()

# ─────────── Cohort prep ───────────
df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly else df["created_at"].dt.date
)

exp = (
    df.loc[df.index.repeat(df["charges_count"].astype(int))]
      .assign(period=lambda d: d.groupby(level=0).cumcount())
)

size = exp[exp.period == 0].groupby("cohort_date").size()
dead = (df[df["next_charge_date"].isna()]
        .groupby("cohort_date").size()
        .reindex(size.index, fill_value=0))
death_pct = (dead / size * 100).round(1)

revenue = (df.groupby("cohort_date")["send_event_amount"].sum()
           .reindex(size.index, fill_value=0).round(2))
ltv = (revenue / size).round(2)

pivot = exp.pivot_table(index="cohort_date", columns="period", aggfunc="size", fill_value=0)
ret   = pivot.div(size, axis=0).mul(100).round(1)
pivot.columns = ret.columns = [f"Period {p}" for p in pivot.columns]

# ─────────── Build table ───────────
death_cell = ("💀 " + death_pct.map(lambda v: f"{v:.1f}%") + " " +
              death_pct.map(bar) + "<br>(" + dead.astype(str) + ")")

disp = pd.DataFrame(index=ret.index, columns=ret.columns)
for idx in ret.index:
    for col in ret.columns:
        disp.loc[idx, col] = ("💀" if (death_pct[idx] == 100 and ret.loc[idx, col] == 0)
                              else f"{ret.loc[idx, col]:.1f}%<br>({pivot.loc[idx, col]})")

combo = disp.copy()
combo.insert(0, "Cohort death", death_cell)
combo.insert(1, "Revenue USD", revenue.map(lambda v: f"${v:,.2f}"))
combo["LTV USD"] = ltv.map(lambda v: f"${v:,.2f}")

# TOTAL row
weighted = lambda s: (s * size).sum() / size.sum()
total = {
    "Cohort death": f"💀 {weighted(death_pct):.1f}% {bar(weighted(death_pct))}",
    "Revenue USD":  f"${revenue.sum():,.2f}",
    "LTV USD":      f"${weighted(ltv):,.2f}",
}
for col in ret.columns:
    total[col] = f"{weighted(ret[col]):.1f}%"
combo.loc["TOTAL"] = total
combo = pd.concat([combo.drop("TOTAL").sort_index(ascending=False), combo.loc[["TOTAL"]]])

# colour helpers
Y_R,Y_G,Y_B=255,212,0; BASE="#202020"; A0,A1=.2,.8
rgba = lambda a: f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"
txt  = lambda a: "black" if a > 0.5 else "white"

header = ["Cohort"] + combo.columns.tolist()
rows, fills, fonts = [], [], []
for ix, row in combo.iterrows():
    rows.append([str(ix)] + row.tolist())
    if ix == "TOTAL":
        fills.append(["#444444"] * len(combo.columns))
        fonts.append(["white"] * len(combo.columns))
        continue
    c, f = ["#1e1e1e", "#333333", "#333333"], ["white"] * 3
    for p in ret.loc[ix].values / 100:
        if p == 0 or pd.isna(p):
            c.append(BASE); f.append("white")
        else:
            a = A0 + (A1 - A0) * p
            c.append(rgba(a)); f.append(txt(a))
    c.append("#333333"); f.append("white")
    fills.append(c); fonts.append(f)

fig_table = go.Figure(go.Table(
    header=dict(values=header, fill_color="#303030",
                font=dict(color="white", size=13), align="center"),
    cells=dict(values=list(map(list, zip(*rows))),
               fill_color=list(map(list, zip(*fills))),
               font=dict(size=13, color=list(map(list, zip(*fonts)))),
               align="center", height=34)
))
fig_table.update_layout(margin=dict(l=10, r=10, t=40, b=10),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig_table, use_container_width=True)

# ─────────── UTM line chart ───────────
new_subs = exp[exp.period == 0].groupby(["cohort_date", utm_col]).size().reset_index(name="New subs")
fig_line = px.line(new_subs, x="cohort_date", y="New subs",
                   color=utm_col, markers=True,
                   title="New subscriptions by UTM source",
                   labels={"cohort_date": "Cohort", utm_col: "UTM source"})
fig_line.update_layout(margin=dict(l=10, r=10, t=40, b=50),
                       legend=dict(orientation="h", y=-0.25),
                       paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_line, use_container_width=True)

# ─────────── Cohort LTV (actual) ───────────
cohort_ltv = (exp.groupby(["cohort_date", "period"])["send_event_amount"]
                .mean().groupby(level=0).cumsum().reset_index(name="LTV"))
plot_df = cohort_ltv[cohort_ltv["cohort_date"].astype(str).isin(sel_cohorts)]
fig_coh = px.line(plot_df, x="period", y="LTV", color="cohort_date",
                  markers=True, title="Cohort LTV (actual)",
                  labels={"period": "Period", "cohort_date": "Cohort"})
fig_coh.update_layout(margin=dict(l=10, r=10, t=40, b=50),
                      legend=dict(orientation="h", y=-0.25),
                      paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_coh, use_container_width=True)

# ─────────── Overall actual LTV curve ───────────
period_rev = exp.groupby("period")["send_event_amount"].mean()
overall_ltv = period_rev.cumsum().round(2)

fig_ltv = px.line(overall_ltv.reset_index(), x="period", y="send_event_amount",
                  markers=True, title="Overall Actual LTV (USD)",
                  labels={"period": "Period", "send_event_amount": "USD"})
fig_ltv.update_layout(margin=dict(l=10, r=10, t=40, b=50),
                      paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_ltv, use_container_width=True)
