import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# ──────────────────────────────────────────
# 0. Load data
# ──────────────────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")

df_raw = load_data(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ──────────────────────────────────────────
# 1. UI filters
# ──────────────────────────────────────────
min_date = df_raw["created_at"].dt.date.min()
max_date = df_raw["created_at"].dt.date.max()

start, end = st.date_input(
    "Date range (created_at):",
    [min_date, max_date],
    min_value=min_date,
    max_value=max_date
)

weekly_toggle = st.checkbox("Weekly cohorts (instead of daily)", value=False)

# UTM source (user_visit.utm_source)
utm_col = "user_visit.utm_source"
if utm_col in df_raw.columns:
    utm_opts = sorted(df_raw[utm_col].dropna().unique())
    selected_utms = st.multiselect("UTM source", utm_opts, default=utm_opts)
else:
    st.info(f"No column “{utm_col}” — UTM filter hidden")
    selected_utms = None

# Price option text
price_col = "price_price_option_text"
if price_col in df_raw.columns:
    price_opts = sorted(df_raw[price_col].dropna().unique())
    selected_prices = st.multiselect("Price option", price_opts, default=price_opts)
else:
    st.info(f"No column “{price_col}” — price filter hidden")
    selected_prices = None

# ──────────────────────────────────────────
# 2. Filter dataframe
# ──────────────────────────────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

if selected_utms is not None:
    df = df[df[utm_col].isin(selected_utms)]
if selected_prices is not None:
    df = df[df[price_col].isin(selected_prices)]

# ──────────────────────────────────────────
# 3. Cohort prep
# ──────────────────────────────────────────
df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly_toggle else
    df["created_at"].dt.date
)

# cohort size
rows = [(row.cohort_date, p)
        for _, row in df.iterrows()
        for p in range(int(row.charges_count))]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])
size = exp[exp.period == 0].groupby("cohort_date").size()

# Cohort death (next_charge_date IS NULL)
dead = (
    df[df["next_charge_date"].isna()]
    .groupby("cohort_date")
    .size()
    .reindex(size.index, fill_value=0)
)
death_pct = (dead / size * 100).round(1)

# LTV USD = avg send_event_amount
ltv = (
    df.groupby("cohort_date")["send_event_amount"].sum()
    .reindex(size.index, fill_value=0)
    / size
).round(2)

# Retention pivots
pivot = exp.pivot_table(index="cohort_date", columns="period", aggfunc="size", fill_value=0)
ret_pct = pivot.div(size, axis=0).mul(100).round(1)

period_cols = [f"Period {p}" for p in pivot.columns]
pivot.columns = period_cols
ret_pct.columns = period_cols

# ──────────────────────────────────────────
# 4. Fancy cells
# ──────────────────────────────────────────
def bar(p: float, width=10):
    filled = int(round(p / 10))
    return "🟥" * filled + "⬜" * (width - filled)

death_cell = (
    "💀 " + death_pct.apply(lambda v: f"{v:.1f}%") + " "
    + death_pct.apply(bar) + "<br>(" + dead.astype(str) + ")"
)

combo = ret_pct.astype(str) + "%<br>(" + pivot.astype(str) + ")"
combo.insert(0, "Cohort size", size)
combo.insert(1, "Cohort death", death_cell)
combo["LTV USD"] = ltv.apply(lambda v: f"${v:,.2f}")
combo = combo.sort_index(ascending=False)

# ──────────────────────────────────────────
# 5. Colors for retention cells
# ──────────────────────────────────────────
Y_R, Y_G, Y_B = 255, 212, 0
BASE = "#202020"
A_MIN, A_MAX = 0.20, 0.80

def rgba(a): return f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"
def txt(a):  return "black" if a > 0.5 else "white"

header = ["Cohort"] + combo.columns.tolist()
rows, fills, fonts = [], [], []

for ix, row in combo.iterrows():
    rows.append([str(ix)] + row.tolist())

    c_row = ["#1e1e1e", "#1e1e1e", "#333333"]
    f_row = ["white"] * 3

    for p in ret_pct.loc[ix].values / 100:
        if pd.isna(p) or p == 0:
            c_row.append(BASE); f_row.append("white")
        else:
            a = A_MIN + (A_MAX - A_MIN)*p
            c_row.append(rgba(a)); f_row.append(txt(a))
    c_row.append("#333333"); f_row.append("white")      # LTV col

    fills.append(c_row); fonts.append(f_row)

vals = list(map(list, zip(*rows)))
fill_cols = list(map(list, zip(*fills)))
font_cols = list(map(list, zip(*fonts)))

# ──────────────────────────────────────────
# 6. Plotly table
# ──────────────────────────────────────────
fig = go.Figure(
    data=[go.Table(
        header=dict(
            values=header,
            fill_color="#303030",
            font=dict(color="white", size=13),
            align="center"),
        cells=dict(
            values=vals,
            fill_color=fill_cols,
            align="center",
            font=dict(size=13, color=font_cols),
            height=34)
    )],
    layout=go.Layout(
        paper_bgcolor="#0f0f0f",
        plot_bgcolor="#0f0f0f",
        margin=dict(l=10, r=10, t=40, b=10))
)

suffix = "weekly" if weekly_toggle else "daily"
st.title(f"Cohort Retention – real_payment = 1 ({suffix})")
st.plotly_chart(fig, use_container_width=True)
