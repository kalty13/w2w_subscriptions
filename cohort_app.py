import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd, re
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ───────────────────────── HELPERS ──────────────────────────
def parse_prices(text: str):
    """Return (trial_price, regular_price) from price_price_option_text."""
    nums = re.findall(r"\d+\.\d+|\d+", text)
    nums = [float(n) for n in nums]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]
    return 0.0, 0.0

def modeled_ltv(p_trial, p_reg, r0, r, period):
    if period == 0:
        return p_trial
    if period == 1:
        return p_trial + p_reg * r0
    return p_trial + p_reg * r0 * (1 - r**period) / (1 - r)

def bar(p,w=10): return "🟥"*int(round(p/10)) + "⬜"*(w-int(round(p/10)))

# ───────────────────────── 0. LOAD DATA ─────────────────────
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

# retention sliders
first_ret_pct  = st.slider("Retention 0 → 1, %", 0, 100, 50, 5)
steady_ret_pct = st.slider("Retention 1+ → next, %", 0, 100, 80, 5)
first_ret, steady_ret = first_ret_pct/100, steady_ret_pct/100

if len(sel_price) != 1:
    st.info("Для модельной LTV-линии выберите ровно один Price option.")

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

size   = exp[exp.period == 0].groupby("cohort_date").size()
dead   = df[df["next_charge_date"].isna()].groupby("cohort_date").size().reindex(size.index, fill_value=0)
death_pct = (dead / size * 100).round(1)
revenue = df.groupby("cohort_date")["send_event_amount"].sum().reindex(size.index, fill_value=0).round(2)
ltv     = (revenue / size).round(2)

pivot = exp.pivot_table(index="cohort_date", columns="period", aggfunc="size", fill_value=0)
ret   = pivot.div(size, axis=0).mul(100).round(1)
pivot.columns = ret.columns = [f"Period {p}" for p in pivot.columns]

# ───────────────────────── 4. BUILD TABLE ──────────────────
death_cell = ("💀 "+death_pct.map(lambda v:f"{v:.1f}%")+" "+death_pct.map(bar)+"<br>("+dead.astype(str)+")")

disp = pd.DataFrame(index=ret.index, columns=ret.columns)
for idx in ret.index:
    for col in ret.columns:
        disp.loc[idx, col] = "💀" if (death_pct.loc[idx]==100 and ret.loc[idx,col]==0) else f"{ret.loc[idx,col]:.1f}%<br>({pivot.loc[idx,col]})"

combo = disp.copy()
combo.insert(0, "Cohort death", death_cell)
combo.insert(1, "Revenue USD", revenue.map(lambda v:f"${v:,.2f}"))
combo["LTV USD"] = ltv.map(lambda v:f"${v:,.2f}")

# TOTAL row
weighted = lambda s: (s*size).sum()/size.sum()
total = {
    "Cohort death": f"💀 {weighted(death_pct):.1f}% {bar(weighted(death_pct))}",
    "Revenue USD":  f"${revenue.sum():,.2f}",
    "LTV USD":      f"${weighted(ltv):,.2f}",
}
for col in ret.columns:
    total[col] = f"{weighted(ret[col]):.1f}%"
combo.loc["TOTAL"] = total
dates_part = combo.drop("TOTAL").sort_index(ascending=False)
combo = pd.concat([dates_part, combo.loc[["TOTAL"]]])

# colouring
Y_R,Y_G,Y_B=255,212,0; BASE="#202020"; A0,A1=.2,.8
rgba = lambda a:f"rgba({Y_R},{Y_G},{Y_B},{a:.2f})"
txt  = lambda a:"black" if a>0.5 else "white"

header = ["Cohort"] + combo.columns.tolist()
rows,fills,fonts=[],[],[]
for ix,row in combo.iterrows():
    rows.append([str(ix)] + row.tolist())
    if ix=="TOTAL":
        c_row=["#444444"]*len(combo.columns); f_row=["white"]*len(combo.columns)
        fills.append(c_row); fonts.append(f_row); continue
    c_row,f_row=["#1e1e1e","#333333","#333333"],["white"]*3
    for p in ret.loc[ix].values/100:
        if p==0 or pd.isna(p): c_row.append(BASE); f_row.append("white")
        else: a=A0+(A1-A0)*p; c_row.append(rgba(a)); f_row.append(txt(a))
    c_row.append("#333333"); f_row.append("white")
    fills.append(c_row); fonts.append(f_row)

fig_table = go.Figure(go.Table(
    header=dict(values=header, fill_color="#303030",
                font=dict(color="white", size=13), align="center"),
    cells=dict(values=list(map(list, zip(*rows))),
               fill_color=list(map(list, zip(*fills))),
               font=dict(size=13, color=list(map(list, zip(*fonts)))),
               align="center", height=34)
))
fig_table.update_layout(margin=dict(l=10,r=10,t=40,b=10),
                        paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.title("Cohort Retention – real_payment = 1")
st.plotly_chart(fig_table, use_container_width=True)

# ───────────────────── 5. LINE CHART BY UTM ─────────────────
new_subs = exp[exp.period==0].groupby(["cohort_date",utm_col]).size().reset_index(name="New subs")
fig_line = px.line(new_subs, x="cohort_date", y="New subs",
                   color=utm_col, markers=True,
                   title="New subscriptions by UTM source",
                   labels={"cohort_date":"Cohort", utm_col:"UTM source"})
fig_line.update_layout(margin=dict(l=10,r=10,t=40,b=50),
                       legend=dict(orientation="h", y=-0.25),
                       paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_line, use_container_width=True)

# ───────────────────── 6. ACTUAL vs MODEL LTV ───────────────
avg_payment = exp[exp.period==0]["send_event_amount"].mean()
overall_size = size.sum()
actual_retain = exp.groupby("period").size().div(overall_size).sort_index()
actual_ltv = (avg_payment*actual_retain.cumsum()).round(2)

model_df = pd.DataFrame({"Period": actual_ltv.index, "Actual LTV": actual_ltv.values})

if len(sel_price)==1:
    trial_p, regular_p = parse_prices(sel_price[0])
    modeled = [round(modeled_ltv(trial_p, regular_p, first_ret, steady_ret, i),2)
               for i in actual_ltv.index]
    model_df[f"Model LTV {first_ret_pct}%→{steady_ret_pct}%"] = modeled
else:
    st.info("Модельная LTV линия скрыта: выберите ровно один Price option.")

fig_ltv = px.line(model_df, x="Period",
                  y=[c for c in model_df.columns if c!="Period"],
                  markers=True, title="Actual vs Modelled LTV (USD)",
                  labels={"value":"USD","variable":""})
fig_ltv.update_layout(margin=dict(l=10,r=10,t=40,b=50),
                      legend=dict(orientation="h", y=-0.25),
                      paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_ltv, use_container_width=True)
