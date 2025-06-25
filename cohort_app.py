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

# UTM (user_visit.utm_source)
utm_col = "user_visit.utm_source"
if utm_col in df_raw.columns:
    utm_opts = sorted(df_raw[utm_col].dropna().unique())
    sel_utm  = st.multiselect("UTM source", utm_opts, default=utm_opts)
else:
    st.info(f"No column “{utm_col}” — UTM filter hidden")
    sel_utm = None

# Price option text  (price.price_option_text)
price_col = "price.price_option_text"
if price_col in df_raw.columns:
    price_opts = sorted(df_raw[price_col].dropna().unique())
    sel_price  = st.multiselect("Price option", price_opts, default=price_opts)
else:
    st.info(f"No column “{price_col}” — price filter hidden")
    sel_price = None

# ───────────────────────── 2. FILTER DATA ───────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

if sel_utm   is not None: df = df[df[utm_col].isin(sel_utm)]
if sel_price is not None: df = df[df[price_col].isin(sel_price)]

# ───────────────────────── 3. COHORT PREP ───────────────────
df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly else df["created_at"].dt.date
)

# cohort size
exp = (df.loc[df.index.repeat(df["charges_count"])]
         .assign(period=lambda d: d.groupby(level=0).cumcount()))
size = exp[exp.period == 0].groupby("cohort_date").size()

# death: next_charge_date IS NULL
dead = (df[df["next_charge_date"].isna()]
        .groupby("cohort_date").size()
        .reindex(size.index, fill_value=0))
death_pct = (dead / size * 100).round(1)

# LTV (mean send_event_amount)
ltv = (
    df.groupby("cohort_date")["send_event_amount"].sum()
      .reindex(size.index, fill_value=0) / size   # ← fill_value по имени
).round(2)

# retention pivots
pivot = exp.pivot_table(index="cohort_date", columns="period",
                        aggfunc="size", fill_value=0)
ret   = pivot.div(size, axis=0).mul(100).round(1)
pivot.columns = ret.columns = [f"Period {p}" for p in pivot.columns]

# ── death-cell (bar) ─────────────────────────────────────────
def bar(p, w=10): return "🟥"*int(round(p/10)) + "⬜"*(w-int(round(p/10)))
death_cell = ("💀 " + death_pct.map(lambda v:f"{v:.1f}%") + " "
              + death_pct.map(bar) + "<br>(" + dead.astype(str) + ")")

# ── final table (no Cohort size) ────────────────────────────
combo = ret.astype(str)+"%<br>("+pivot.astype(str)+")"
combo.insert(0, "Cohort death", death_cell)
combo["LTV USD"] = ltv.map(lambda v: f"${v:,.2f}")
combo = combo.sort_index(ascending=False)

# ───────────────────────── 4. COLOURS ───────────────────────
Y_R, Y_G, Y_B = 255,212,0; BASE="#202020"; A0,A1 = .2,.8
def rgba(a): f=f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"; return f
def txt(a):  "black" if a>0.5 else "white"

header = ["Cohort"]+combo.columns.tolist()
rows,fills,fonts=[],[],[]
for ix,row in combo.iterrows():
    rows.append([str(ix)]+row.tolist())
    c,f=["#1e1e1e","#333333"],["white","white"]          # Cohort / death
    for p in ret.loc[ix].values/100:
        if pd.isna(p) or p==0: c.append(BASE); f.append("white")
        else:
            a=A0+(A1-A0)*p; c.append(rgba(a)); f.append("black" if a>0.5 else "white")
    c.append("#333333"); f.append("white")               # LTV
    fills.append(c); fonts.append(f)

vals  = list(map(list, zip(*rows)))
fill_cols = list(map(list, zip(*fills)))
font_cols = list(map(list, zip(*fonts)))

fig_table = go.Figure(go.Table(
    header=dict(values=header, fill_color="#303030",
                font=dict(color="white", size=13), align="center"),
    cells=dict(values=vals, fill_color=fill_cols,
               font=dict(size=13, color=font_cols),
               align="center", height=34)
))
fig_table.update_layout(margin=dict(l=10,r=10,t=40,b=10),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig_table, use_container_width=True)

# ───────────────────────── 5. CURVE BELOW TABLE ─────────────
sel_cohort = st.selectbox("Select cohort for curves", combo.index.astype(str))

curve_df = pd.DataFrame({
    "Period": range(len(pivot.columns)),
    "Retention %": ret.loc[sel_cohort].values,
    "LTV USD": (pivot.loc[sel_cohort].cumsum()
                * df["send_event_amount"].mean() / size[sel_cohort]).round(2)
})

fig_curve = px.line(curve_df, x="Period", y=["Retention %","LTV USD"],
                    markers=True, labels={"value":"","variable":""},
                    title=f"Retention & LTV curves — cohort {sel_cohort}")
fig_curve.update_layout(legend=dict(orientation="h", y=-0.25),
                        margin=dict(l=10,r=10,t=40,b=50),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")

st.plotly_chart(fig_curve, use_container_width=True)
