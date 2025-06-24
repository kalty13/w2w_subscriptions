import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
import numpy as np
from pathlib import Path

# ───────────────────────────────
# 0. Чтение файла с подписками
# ───────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"     # если CSV — поменяй suffix

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")                    # CSV → sep=',' или убери

df = load_data(FILE)

# ───────────────────────────────
# 1. Подготовка данных
# ───────────────────────────────
df = df[df["real_payment"] == 1]                      # только реальные оплаты
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

# красивые названия колонок
period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

# "%\n(abs)"
combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)                  # первый столбец
combo = combo.sort_index(ascending=False)

# ───────────────────────────────
# 2. Градиент заливки по %
# ───────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
cohort_labels = combo.index.astype(str).tolist()      # превращаем даты в строки
cells = [cohort_labels] + [
    combo[col].tolist() for col in combo.columns
]


pct_matrix = pivot_pct.reindex(combo.index).values / 100.0
cmap = cm.get_cmap("Reds")

fill_colors = [["white"] * len(header)]               # строка заголовков
for row in pct_matrix:
    row_colors = ["white"]                            # столбец Cohort size
    row_colors += [
        f"rgba{tuple((np.array(cmap(v)) * 255).astype(int))}"
        for v in row
    ]
    fill_colors.append(row_colors)

# ───────────────────────────────
# 3. Рисуем Plotly Table
# ───────────────────────────────
fig = go.Figure(
    data=[
        go.Table(
            header=dict(
                values=header,
                fill_color="#202020",
                font=dict(color="white", size=12),
                align="center"
            ),
            cells=dict(
                values=cells,
                fill_color=fill_colors,
                align="center",
                font=dict(size=12),
                height=30
            )
        )
    ],
    layout=go.Layout(margin=dict(l=0, r=0, t=30, b=0))
)

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig, use_container_width=True)
