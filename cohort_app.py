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

pivot_subs = exp.pivot_table(
    index="cohort_date", columns="period", aggfunc="size", fill_value=0
)
pivot_pct = pivot_subs.div(size, axis=0).mul(100).round(1)

st.title("Cohort Retention (real_payment = 1)")

view = st.radio("Режим:", ("Heat-map %", "Абсолюты + %"))

if view == "Heat-map %":
    fig = px.imshow(
        pivot_pct.sort_index(ascending=False),
        labels=dict(x="Period", y="Cohort", color="Ret %"),
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="Reds"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    combo = pivot_subs.astype(int).astype(str) + " (" + pivot_pct.astype(str) + "%)"
    st.dataframe(
        combo.sort_index(ascending=False),
        height=600,
        use_container_width=True
    )
