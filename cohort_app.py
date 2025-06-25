import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path
from datetime import date

# ──────────────────────────────────────────
# 0. Загрузка TSV (CSV → уберите sep='\t')
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

# ──────────────────────────────────────────
# 2. Фильтрация и подготовка
# ──────────────────────────────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

if weekly_toggle:
    df["cohort_date"] = df["created_at"].dt.to_period("W").apply(
        lambda r: r.start_time.date()
    )
else:
    df["cohort_date"] = df["created_at"].dt.date

# Cohort-size (Period 0)
rows = [
    (row.cohort_date, period)
    for _, row in df.iterrows()
    for period in range(int(row.charges_count))
]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])
size = exp[exp.period == 0].groupby("cohort_date").size()

# Cohort-death: статус canceled
canceled = (
    df[df["status"].str.lower() == "canceled"]
    .groupby("cohort_date")
    .size()
    .reindex(size.index, fill_value=0)
)
death_pct = (canceled / size * 100).round(1)

# Pivot таблицы
pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)
combo.insert(1, "Cohort death", death_pct.astype(str) + "%<br>(" + canceled.astype(str) + ")")
combo = combo.sort_index(ascending=False)

# ──────────────────────────────────────────
# 3. Формируем values и цвета
# ──────────────────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
table_rows, row_colors, font_rows = [], [], []
cmap = cm.get_cmap("YlGnBu_r")       # спокойный градиент
BASE = "#202020"

def txt_color(r, g, b):
    return "black" if (0.299*r + 0.587*g + 0.114*b) > 128 else "white"

for ix, row in combo.iterrows():
    # values
    table_rows.append([str(ix)] + row.tolist())

    pct_vals = pivot_pct.loc[ix].values / 100.0
    color_row = ["#1e1e1e", "#1e1e1e", "#333333"]  # Cohort / size / death
    font_row  = ["white", "white", "white"]

    for p in pct_vals:
        if pd.isna(p) or p == 0:
            color_row.append(BASE)
            font_row.append("white")
        else:
            r, g, b, a = cmap(0.25 + 0.75 * p)     # тёмная часть палитры
            color_row.append(
                f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{max(a,0.8):.2f})"
            )
            font_row.append(txt_color(int(r*255), int(g*255), int(b*255)))
    row_colors.append(color_row)
    font_rows.append(font_row)

values_cols = list(map(list, zip(*table_rows)))
colors_cols = list(map(list, zip(*row_colors)))
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
            height=32
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
