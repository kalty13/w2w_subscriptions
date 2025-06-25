import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path

# ──────────────────────────────────────────
# 0. Чтение TSV (CSV → уберите sep="\t")
# ──────────────────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t")

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
# 2. Подготовка данных
# ──────────────────────────────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

# Cohort: daily или понедельник недели
if weekly_toggle:
    df["cohort_date"] = (
        df["created_at"]
        .dt.to_period("W")
        .apply(lambda r: r.start_time.date())
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

# Cohort-death
canceled = (
    df[df["status"].str.lower() == "canceled"]
    .groupby("cohort_date")
    .size()
    .reindex(size.index, fill_value=0)
)
death_pct = (canceled / size * 100).round(1)

# Pivot абсолюты / проценты
pivot_subs = exp.pivot_table(
    index="cohort_date",
    columns="period",
    aggfunc="size",
    fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

# Композит «%<br>(abs)»
combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)
combo.insert(
    1,
    "Cohort death",
    death_pct.astype(str) + "%<br>(" + canceled.astype(str) + ")"
)
combo = combo.sort_index(ascending=False)

# ──────────────────────────────────────────
# 3. Цвета + авто-контраст
# ──────────────────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
cmap   = cm.get_cmap("viridis")          # спокойный градиент
BASE   = "#202020"                       # фон пустых клеток

def rgba_str(r, g, b, a) -> str:
    return f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{a:.2f})"

def color_for(p: float) -> str:
    """ p∊[0,1] → цвет viridis со сильной прозрачностью """
    r, g, b, _ = cmap(p)
    alpha = 0.25 + 0.4 * p               # 0 → 0.25, 1 → 0.65
    return rgba_str(r, g, b, alpha)

def txt_color(r, g, b) -> str:
    # YIQ яркость: >150 → чёрный текст, иначе белый
    return "black" if (0.299*r + 0.587*g + 0.114*b) > 150 else "white"

table_rows, fill_rows, font_rows = [], [], []

for ix, row in combo.iterrows():
    table_rows.append([str(ix)] + row.tolist())

    pct_vals = pivot_pct.loc[ix].values / 100.0
    c_row, f_row = ["#1e1e1e", "#1e1e1e", "#333333"], ["white"]*3

    for p in pct_vals:
        if pd.isna(p) or p == 0:
            c_row.append(BASE)
            f_row.append("white")
        else:
            rgba   = color_for(p)
            r, g, b = [int(x) for x in rgba[5:-1].split(",")[:3]]
            c_row.append(rgba)
            f_row.append(txt_color(r, g, b))

    fill_rows.append(c_row)
    font_rows.append(f_row)

# Транспонируем в колонки (Plotly Table ждёт col-major)
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
