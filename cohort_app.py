import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ───────────────────────── 0. LOAD ──────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(p): return pd.read_csv(p, sep="\t")

df_raw = load_data(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ───────────────────────── 1. FILTER UI ─────────────────────
min_d, max_d = df_raw["created_at"].dt.date.agg(["min", "max"])
start, end   = st.date_input("Date range", [min_d, max_d], min_d, max_d)
weekly       = st.checkbox("Weekly cohorts", False)

utm_col, price_col = "user_visit.utm_source", "price.price_option_text"
utm_opts   = sorted(df_raw[utm_col].dropna().unique())
price_opts = sorted(df_raw[price_col].dropna().unique())

sel_utm   = st.multiselect("UTM source", utm_opts, default=utm_opts)
sel_price = st.multiselect("Price option", price_opts, default=price_opts)

model_r_pct = st.multiselect(
    "Model retention per period (%)", list(range(10, 101, 10)), default=[80, 60, 40]
)
model_r = [v/100 for v in model_r_pct]

# ───────────────────────── 2. FILTER DATA ───────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end)) &
    (df_raw[utm_col].isin(sel_utm)) &
    (df_raw[price_col].isin(sel_price))
].copy()

# ───────────────────────── 3. COHORT PREP ───────────────────
df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly else df["created_at"].dt.date
)

exp = (
    df.loc[df.index.repeat(df["charges_count"].astype(int))]
      .assign(period=lambda d: d.groupby(level=0).cumcount())
)

size = exp[exp.period == 0].groupby("cohort_date").size()

# death by next_charge_date IS NULL
dead = (
    df[df["next_charge_date"].isna()]
      .groupby("cohort_date").size()
      .reindex(size.index, fill_value=0)
)
death_pct = (dead / size * 100).round(1)

# Revenue & LTV
revenue = (
    df.groupby("cohort_date")["send_event_amount"].sum()
      .reindex(size.index, fill_value=0)
).round(2)

ltv = (revenue / size).round(2)

# retention matrix
pivot = exp.pivot_table(index="cohort_date", columns="period",
                        aggfunc="size", fill_value=0)
ret   = pivot.div(size, axis=0).mul(100).round(1)
pivot.columns = ret.columns = [f"Period {p}" for p in pivot.columns]

# ───────────────────────── 4. BUILD TABLE ──────────────────
def bar(p,w=10): return "🟥"*int(round(p/10)) + "⬜"*(w-int(round(p/10)))

death_cell = (
    "💀 "+death_pct.map(lambda v:f"{v:.1f}%")+" "
    + death_pct.map(bar)+"<br>("+dead.astype(str)+")"
)

# пользовательские отображения retention (%+abs) и 💀 при 100 % смерти
disp = pd.DataFrame(index=ret.index, columns=ret.columns)
for idx in ret.index:
    for col in ret.columns:
        if death_pct.loc[idx] == 100 and ret.loc[idx, col] == 0:
            disp.loc[idx, col] = "💀"
        else:
            disp.loc[idx, col] = f"{ret.loc[idx,col]:.1f}%<br>({pivot.loc[idx,col]})"

combo = disp.copy()
combo.insert(0, "Cohort death", death_cell)
combo.insert(1, "Revenue USD", revenue.map(lambda v:f"${v:,.2f}"))
combo["LTV USD"] = ltv.map(lambda v:f"${v:,.2f}")

# ── TOTAL ROW ───────────────────────────────────────────────
weighted = lambda s: (s*size).sum()/size.sum()
total = {
    "Cohort death": f"💀 {weighted(death_pct):.1f}% {bar(weighted(death_pct))}",
    "Revenue USD":  f"${revenue.sum():,.2f}",
    "LTV USD":      f"${weighted(ltv):,.2f}",
}
for col in ret.columns:
    total[col] = f"{weighted(ret[col]):.1f}%"
combo.loc["TOTAL"] = total                      # строка-итог
combo = combo.sort_index(ascending=False)       # TOTAL снизу

# ────────────────── 5. COLOURING & PLOT TABLE ──────────────
Y_R,Y_G,Y_B=255,212,0; BASE="#202020"; A0,A1=.2,.8
rgba = lambda a:f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"
txt  = lambda a:"black" if a>0.5 else "white"

header = ["Cohort"] + combo.columns.tolist()
rows,fills,fonts = [], [], []

for ix,row in combo.iterrows():
    rows.append([str(ix)] + row.tolist())

    if ix == "TOTAL":                          # однотонная строка
        c_row = ["#444444"] * len(combo.columns)
        f_row = ["white"]   * len(combo.columns)
        fills.append(c_row); fonts.append(f_row)
        continue

    c_row,f_row = ["#1e1e1e","#333333","#333333"], ["white"]*3  # Cohort/death/revenue
    for p in ret.loc[ix].values/100:
        if p==0 or pd.isna(p): c_row.append(BASE); f_row.append("white")
        else: a=A0+(A1-A0)*p; c_row.append(rgba(a)); f_row.append(txt(a))
    c_row.append("#333333"); f_row.append("white")              # LTV
    fills.append(c_row); fonts.append(f_row)

vals  = list(map(list, zip(*rows)))
fills = list(map(list, zip(*fills)))
fonts = list(map(list, zip(*fonts)))

fig_table = go.Figure(go.Table(
    header=dict(values=header, fill_color="#303030",
                font=dict(color="white", size=13), align="center"),
    cells=dict(values=vals, fill_color=fills,
               font=dict(size=13, color=fonts),
               align="center", height=34)
))
fig_table.update_layout(margin=dict(l=10,r=10,t=40,b=10),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")

st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig_table, use_container_width=True)

# ───────────────────── 6. LINE CHART BY UTM ─────────────────
new_subs = (
    exp[exp.period == 0]
      .groupby(["cohort_date", utm_col]).size()
      .reset_index(name="New subs")
)

fig_line = px.line(new_subs, x="cohort_date", y="New subs",
                   color=utm_col, markers=True,
                   title="New subscriptions by UTM source",
                   labels={"cohort_date":"Cohort", utm_col:"UTM source"})
fig_line.update_layout(margin=dict(l=10,r=10,t=40,b=50),
                       legend=dict(orientation="h", y=-0.25),
                       paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_line, use_container_width=True)

# ───────────────────── 7. ACTUAL vs MODEL LTV ───────────────
avg_payment = exp[exp.period == 0]["send_event_amount"].mean()
overall_size = size.sum()
actual_retain = exp.groupby("period").size().div(overall_size).sort_index()
actual_ltv = (avg_payment * actual_retain.cumsum()).round(2)

model_df = pd.DataFrame({"Period": actual_ltv.index,
                         "Actual LTV": actual_ltv.values})
for r in model_r:
    model_df[f"Model {int(r*100)}%"] = [
        round(avg_payment * sum(r**k for k in range(p+1)), 2)
        for p in model_df["Period"]
    ]

fig_ltv = px.line(model_df, x="Period",
                  y=[c for c in model_df.columns if c != "Period"],
                  markers=True,
                  title="Actual vs Modelled LTV (USD)",
                  labels={"value":"USD", "variable":""})
fig_ltv.update_layout(margin=dict(l=10,r=10,t=40,b=50),
                      legend=dict(orientation="h", y=-0.25),
                      paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_ltv, use_container_width=True)
