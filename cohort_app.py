import streamlit as st
st.set_page_config(
    layout="wide",
    page_title="Cohort Retention"
)

import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path
from datetime import date

# ──────────────────────────────────────────
# 0. Загрузка данных
# ──────────────────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"      # CSV? → меняй расширение

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

weekly_toggle = st.checkbox(
    "Weekly cohorts (instead of daily)",
    value=False
)

# ──────────────────────────────────────────
# 2. Фильтрация и подготовка
# ──────────────────────────────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

if weekly_toggle:
    # cohort = понедельник недели
    df["cohort_date"] = df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
else:
    df["cohort_date"] = df["created_at"].dt.date

rows = [
    (row.cohort_date, period)
    for _, row in df.iterrows()
    for period in range(int(row.charges_count))
]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])

size = exp[exp.period == 0].groupby("cohort_date").size()

pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)
combo = combo.sort_index(ascending=False)

# ──────────────────────────────────────────
# 3. colours + table
# ──────────────────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
table_rows, row_colors = [], []
cmap = cm.get_cmap("YlGnBu_r")             # спокойный сине-зелёный
BASE = "#202020"

for ix, row in combo.iterrows():
    table_rows.append([str(ix)] + row.tolist())
    pct_vals = pivot_pct.loc[ix].values / 100.0
    color_row = ["#1e1e1e", "#1e1e1e"]     # cohort / size
    for p in pct_vals:
        if pd.isna(p) or p == 0:
            color_row.append(BASE)
        else:
            r, g, b, a = cmap(p)
            color_row.append(
                f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{max(a,0.6):.2f})"
            )
    row_colors.append(color_row)

values_cols = list(map(list, zip(*table_rows)))
colors_cols = list(map(list, zip(*row_colors)))

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
            font=dict(size=13),
            height=32
        )
    )],
    layout=go.Layout(
        paper_bgcolor="#0f0f0f",
        plot_bgcolor="#0f0f0f",
        margin=dict(l=10, r=10, t=40, b=10)
    )
)

title_suffix = "weekly" if weekly_toggle else "daily"
st.title(f"Cohort Retention – real_payment = 1 ({title_suffix})")
st.plotly_chart(fig, use_container_width=True)
