import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path

# ───────────────────────────────
# 0. Чтение файла
# ───────────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"      # CSV? смени расширение

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")                    # CSV → sep="," или убрать

df = load_data(FILE)

# ───────────────────────────────
# 1. Подготовка данных
# ───────────────────────────────
df = df[df["real_payment"] == 1]                      # только real_payment=1
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
pivot_pct.columns  = period_c
