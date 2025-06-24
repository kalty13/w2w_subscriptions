import streamlit as st
st.set_page_config(
    layout="wide",
    page_title="Cohort Retention"
)

import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path

# ───────────────────────────────
# 0. Чтение локального файла
# ───────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"        # CSV? → поменяй расширение

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    # CSV → убери sep="\t" или замени на ","
    return pd.read_csv(p, sep="\t")

df = load_data(FILE)

# ───────────────────────────────
# 1. Подготовка данных
# ───────────────────────────────
df = df[df["real_payment"] == 1]
df["cohort_date"] = pd.to_datetime(df["created_at"]).dt.date

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
combo = combo.sort_index(ascending=False)                 # свежие когорты сверху

# ───────────────────────────────
# 2. Формируем values и цвета
# ───────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
table_rows, row_colors = [], []
cmap = cm.get_cmap("RdYlGn_r")            # зелёный → жёлтый → красный
BASE = "#262626"                          # тёмный фон для пустых/нулевых

for ix, row in combo.iterrows():
    # values
    table_rows.append([str(ix)] + row.tolist())

    # цвета
    pct_vals = pivot_pct.loc[ix].values / 100.0
    color_row = ["#1e1e1e", "#1e1e1e"]    # Cohort + Cohort size

    for p in pct_vals:
        if pd.isna(p) or p == 0:
            color_row.append(BASE)
        else:
            r, g, b, a = cmap(p)
            color_row.append(
                f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{max(a,0.6):.2f})"
            )
    row_colors.append(color_row)

# Транспонируем: Plotly ждёт list-of-columns
values_cols = list(map(list, zip(*table_rows)))
colors_cols = list(map(list, zip(*row_colors)))

# ───────────────────────────────
# 3. Plotly Table
# ───────────────────────────────
fig = go.Figure(
    data=[go.Table(
        header=dict(
            values=header,
            fill_color="#202020",
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
        paper_bgcolor="#0f0f0f",        # фон страницы
        plot_bgcolor="#0f0f0f",
        margin=dict(l=10, r=10, t=40, b=10)
    )
)

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig, use_container_width=True)
