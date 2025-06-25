import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# ──────────────────────────────────────────
# 0. Загрузка TSV  (CSV → уберите sep='\t')
# ──────────────────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")

df_raw = load_data(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ──────────────────────────────────────────
# 1. UI-фильтры
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

# UTM source
utm_opts = sorted(df_raw["utm_source"].dropna().unique())
selected_utms = st.multiselect("UTM source", utm_opts, default=utm_opts)

# Subscription (price_id)
sub_opts = sorted(df_raw["price_id"].dropna().unique())
selected_subs = st.multiselect("Subscription ID (price_id)", sub_opts, default=sub_opts)

# ──────────────────────────────────────────
# 2. Подготовка данных
# ──────────────────────────────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end)) &
    (df_raw["utm_source"].isin(selected_utms)) &
    (df_raw["price_id"].isin(selected_subs))
].copy()

# cohort_date
if weekly_toggle:
    df["cohort_date"] = (
        df["created_at"].dt.to_period("W")
        .apply(lambda r: r.start_time.date())
    )
else:
    df["cohort_date"] = df["created_at"].dt.date

# cohort size (Period 0)
rows = [
    (row.cohort_date, p)
    for _, row in df.iterrows()
    for p in range(int(row.charges_count))
]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])
size = exp[exp.period == 0].groupby("cohort_date").size()

# cohort death  (нет next_charge_date)
mask_dead = df["next_charge_date"].isna()
canceled = (
    df[mask_dead]
    .groupby("cohort_date")
    .size()
    .reindex(size.index, fill_value=0)
)
death_pct = (canceled / size * 100).round(1)

# LTV (USD) — средняя выручка на подписку в когорте
ltv = (
    df.groupby("cohort_date")["total_revenue_usd"].sum()
    .reindex(size.index, fill_value=0)
    / size
).round(2)

# Pivot retention
pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

# ── формат death-ячейки с баром 🟥/⬜ ──────────────────────────────
def bar(p: float, width: int = 10) -> str:
    filled = int(round(p / 10))
    return "🟥" * filled + "⬜" * (width - filled)

death_cell = (
    "💀 "
    + death_pct.astype(lambda v: f"{v:.1f}%").astype(str)
    + " "
    + death_pct.apply(bar)
    + "<br>("
    + canceled.astype(str)
    + ")"
)

# ── финальная таблица combo ───────────────────────────────────────
combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)
combo.insert(1, "Cohort death", death_cell)
combo["LTV USD"] = ltv.apply(lambda v: f"${v:,.2f}")
combo = combo.sort_index(ascending=False)

# ──────────────────────────────────────────
# 3. Заливка retention (жёлтый, прозрачный)
# ──────────────────────────────────────────
Y_R, Y_G, Y_B = 255, 212, 0
BASE = "#202020"
ALPHA_MIN, ALPHA_MAX = 0.20, 0.80

def rgba(alpha: float) -> str:
    return f"rgba({Y_R},{Y_G},{Y_B},{alpha:.2f})"

def txt_color(alpha: float) -> str:
    return "black" if alpha > 0.5 else "white"

header = ["Cohort"] + combo.columns.tolist()
table_rows, fill_rows, font_rows = [], [], []

for ix, row in combo.iterrows():
    table_rows.append([str(ix)] + row.tolist())

    pct_vals = pivot_pct.loc[ix].values / 100.0
    #     Cohort   size   death   …retention…   LTV
    c_row = ["#1e1e1e", "#1e1e1e", "#333333"]
    f_row = ["white",   "white",   "white"]

    for p in pct_vals:
        if pd.isna(p) or p == 0:
            c_row.append(BASE)
            f_row.append("white")
        else:
            alpha = ALPHA_MIN + (ALPHA_MAX - ALPHA_MIN) * p
            c_row.append(rgba(alpha))
            f_row.append(txt_color(alpha))
    # LTV колонка
    c_row.append("#333333")
    f_row.append("white")

    fill_rows.append(c_row)
    font_rows.append(f_row)

# col-major для Plotly
values_cols = list(map(list, zip(*table_rows)))
colors_cols = list(map(list, zip(*fill_rows)))
fonts_cols  = list(map(list, zip(*font_rows)))

# ──────────────────────────────────────────
# 4. Plotly Table
# ──────────────────────────────────────────
fig = go.Figure(
    data=[go.Table(
        header=dict(
            values=header,
            fill_color="#303030",
            font=dict(color="white", size=13),
            align="center"
        ),
        cells=dict(
            values=values_cols,
            fill_color=colors_cols,
            align="center",
            font=dict(size=13, color=fonts_cols),
            height=34
        )
    )],
    layout=go.Layout(
        paper_bgcolor="#0f0f0f",
        plot_bgcolor="#0f0f0f",
        margin=dict(l=10, r=10, t=40, b=10)
    )
)

suffix = "weekly" if weekly_toggle else "daily"
st.title(f"Cohort Retention – real_payment = 1 ({suffix})")
st.plotly_chart(fig, use_container_width=True)
