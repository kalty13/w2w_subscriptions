import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ───────────────────────── 0. LOAD  ─────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(p): return pd.read_csv(p, sep="\t")

df_raw = load_data(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ───────────────────────── 1. FILTER UI ─────────────────────
min_d, max_d = df_raw["created_at"].dt.date.agg(["min", "max"])
start, end   = st.date_input("Date range", [min_d, max_d], min_d, max_d)
weekly       = st.checkbox("Weekly cohorts", False)

utm_col = "user_visit.utm_source"
sel_utm = st.multiselect("UTM source", sorted(df_raw[utm_col].dropna().unique()),
                         default=sorted(df_raw[utm_col].dropna().unique()))

price_col = "price_price_option_text"
sel_price = st.multiselect("Price option", sorted(df_raw[price_col].dropna().unique()),
                           default=sorted(df_raw[price_col].dropna().unique()))

# ───────────────────────── 2. FILTER DATA ───────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end)) &
    (df_raw[utm_col].isin(sel_utm)) &
    (df_raw[price_col].isin(sel_price))
].copy()

df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly else df["created_at"].dt.date
)

# size (для расчётов — в таблице не выводим)
exp = (df.loc[df.index.repeat(df["charges_count"])]
         .assign(period=lambda d: d.groupby(level=0).cumcount()))
size = exp[exp.period == 0].groupby("cohort_date").size()

# death
dead = (df[df["next_charge_date"].isna()]
        .groupby("cohort_date").size()
        .reindex(size.index, fill_value=0))
death_pct = (dead / size * 100).round(1)

# LTV
ltv = (df.groupby("cohort_date")["send_event_amount"].sum().reindex(size.index, 0) / size).round(2)

# retention pivots
pivot = exp.pivot_table(index="cohort_date", columns="period", aggfunc="size", fill_value=0)
ret = pivot.div(size, axis=0).mul(100).round(1)
period_cols = [f"Period {p}" for p in pivot.columns]
pivot.columns, ret.columns = period_cols, period_cols

# ─────────────── 3. BUILD TABLE CELLS (no Cohort size) ─────
def bar(p): return "🟥"*int(round(p/10)) + "⬜"* (10-int(round(p/10)))
death_cell = ("💀 " + death_pct.map(lambda v:f"{v:.1f}%") + " " +
              death_pct.map(bar) + "<br>("+dead.astype(str)+")")

combo = ret.astype(str)+"%<br>("+pivot.astype(str)+")"
combo.insert(0, "Cohort death", death_cell)
combo["LTV USD"] = ltv.map(lambda v: f"${v:,.2f}")
combo = combo.sort_index(ascending=False)

# colours
Y_R, Y_G, Y_B = 255,212,0; BASE="#202020"
def rgba(a):  return f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"
def txt(a):   return "black" if a>0.5 else "white"
A0,A1 = .2,.8

header = ["Cohort"]+combo.columns.tolist()
rows,fills,fonts=[],[],[]
for ix,row in combo.iterrows():
    rows.append([str(ix)]+row.tolist())
    c,f=["#1e1e1e","#333333"],["white","white"]          # Cohort / death
    for p in ret.loc[ix].values/100:
        if pd.isna(p) or p==0: c.append(BASE); f.append("white")
        else:
            a=A0+(A1-A0)*p; c.append(rgba(a)); f.append(txt(a))
    c.append("#333333"); f.append("white")               # LTV
    fills.append(c); fonts.append(f)

vals  = list(map(list, zip(*rows)))
fills = list(map(list, zip(*fills)))
fonts = list(map(list, zip(*fonts)))

fig_table = go.Figure(go.Table(
    header=dict(values=header, fill_color="#303030",
                font=dict(color="white", size=13), align="center"),
    cells=dict(values=vals, fill_color=fills,
               font=dict(size=13, color=fonts), align="center",
               height=34)
))
fig_table.update_layout(margin=dict(l=10,r=10,t=40,b=10),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig_table, use_container_width=True)

# ───────────────────────── 4. LINE CHART UNDER TABLE ───────
selected_cohort = st.selectbox("Select cohort for curves",
                               combo.index.astype(str))

curve_df = pd.DataFrame({
    "Period": range(len(period_cols)),
    "Retention %": ret.loc[selected_cohort].values,
    "LTV USD": (pivot.loc[selected_cohort]
                .cumsum()*df["send_event_amount"].mean()/size[selected_cohort]).round(2)
})

fig_curve = px.line(curve_df, x="Period", y=["Retention %", "LTV USD"],
                    markers=True,
                    labels={"value":"","variable":""},
                    title=f"Retention & LTV curves — cohort {selected_cohort}")
fig_curve.update_layout(legend=dict(orientation="h", y=-0.25),
                        margin=dict(l=10,r=10,t=50,b=50),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")

st.plotly_chart(fig_curve, use_container_width=True)
