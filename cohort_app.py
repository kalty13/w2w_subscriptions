import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

FILE = Path(__file__).parent / "subscriptions.tsv"   # тот самый файл

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")   # если CSV → sep="," или вообще не указывать

df = load_data(FILE)
df = df[df["real_payment"] == 1]                  # фильтр
df["cohort_date"] = pd.to_datetime(df["created_at"]).dt.date

rows = [
    (row.cohort_date, period)
    for _, row in df.iterrows()
    for period in range(int(row.charges_count))
]
exp = pd.DataFrame(rows, columns=["cohort_date", "period"])
size = exp[exp.period == 0].groupby("cohort_date").size()

# ────────────────────────────────
# СТАРЫЙ БЛОК (pivot_subs / pct) ЗАМЕНЯЕМ НА НОВЫЙ
# ────────────────────────────────
pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

# 1) красивое имя колонок
pivot_subs.columns = [f"Period {p}" for p in pivot_subs.columns]
pivot_pct.columns  = [f"Period {p}" for p in pivot_pct.columns]

# 2) формируем “%  (abs)” строкой c переносом
combo = pivot_pct.astype(str) + "%\n(" + pivot_subs.astype(str) + ")"

# 3) добавляем первый столбец Cohort size
combo.insert(0, "Cohort size", size)

# 4) сортировка – свежие когорты сверху
combo = combo.sort_index(ascending=False)

# ────────────────────────────────
# ВЫВОД
# ────────────────────────────────
st.title("Cohort Retention – real_payment = 1")

st.dataframe(
    combo,
    height=700,
    use_container_width=True
)

