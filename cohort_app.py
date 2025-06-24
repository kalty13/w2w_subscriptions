import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path

# ───────────────────────────────
# 0. Чтение локального файла
# ───────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"     # CSV? — измени расширение

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    # Если данные CSV → убери sep="\t"
    return pd.read_csv(p, sep="\t")

df = load_data(FILE)

# ___________
# ───────────────────────────────
# 1. Подготовка данных
# ───────────────────────────────
df = df[df["real_payment"] == 1]                       # только реальные оплаты
df["cohort_date"] = pd.to_datetime(df["created_at"]).dt.date

# разворачиваем каждую подписку на все оплаченные периоды
rows = [
    (row.cohort_date, period)
    for _, row in df.iterrows()
    for period in range(int(row.charges_count))
]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])

# размер когорты (Period 0)
size = exp[exp.period == 0].groupby("cohort_date").size()

# абсолюты и проценты
pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

# Заголовки «Period 0», «Period 1», …
period_cols = [f"Period {p}" for p in pivot_subs.columns]
pivot_subs.columns = period_cols
pivot_pct.columns  = period_cols

# строка «XX.X %<br>(NNN)»
combo = pivot_pct.astype(str) + "%<br>(" + pivot_subs.astype(str) + ")"
combo.insert(0, "Cohort size", size)                   # первый столбец
combo = combo.sort_index(ascending=False)              # свежие когорты сверху

# ───────────────────────────────
# 2. Формируем values и заливку
# ───────────────────────────────
header = ["Cohort"] + combo.columns.tolist()
table_rows, row_colors = [], []
cmap = cm.get_cmap("Reds")

for ix, row in combo.iterrows():
    # values
    table_rows.append([str(ix)] + row.tolist())

    # цвета: первые два столбца белые, дальше — градиент по %
    pct_vals = pivot_pct.loc[ix].values / 100.0
    color_row = ["white", "white"] + [
        f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{a:.3f})"
        for r, g, b, a in (cmap(p) for p in pct_vals)
    ]
    row_colors.append(color_row)

# транспонируем: Plotly ждёт list-of-columns
values_cols = list(map(list, zip(*table_rows)))
colors_cols = list(map(list, zip(*row_colors)))

# ───────────────────────────────
# 3. Рисуем Plotly Table
# ───────────────────────────────
fig = go.Figure(
    data=[go.Table(
        header=dict(
            values=header,
            fill_color="#202020",
            font=dict(color="white", size=12),
            align="center"
        ),
        cells=dict(
            values=values_cols,
            fill_color=colors_cols,
            align="center",
            font=dict(size=12),
            height=30
        )
    )],
    layout=go.Layout(margin=dict(l=0, r=0, t=30, b=0))
)

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig, use_container_width=True)
