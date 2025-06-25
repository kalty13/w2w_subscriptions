import streamlit as st
st.set_page_config(layout="wide", page_title="Cohort Retention")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from plotly.express import _core as pxcore          # iso-таблица

# ───────────────────────── 0. LOAD ──────────────────────────
FILE = Path(__file__).parent / "subscriptions.tsv"

@st.cache_data(show_spinner=False)
def load_data(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t")

df_raw = load_data(FILE)
df_raw["created_at"] = pd.to_datetime(df_raw["created_at"])

# ───────────────────────── 1. FILTER UI ─────────────────────
min_d, max_d = df_raw["created_at"].dt.date.agg(["min", "max"])
start, end   = st.date_input("Date range", [min_d, max_d], min_d, max_d)
weekly       = st.checkbox("Weekly cohorts", False)

utm_col     = "user_visit.utm_source"
price_col   = "price.price_option_text"
country_col = "user_visit.user_country_code"   # ISO-2

# UTM filter
if utm_col in df_raw.columns:
    utm_opts = sorted(df_raw[utm_col].dropna().unique())
    sel_utm  = st.multiselect("UTM source", utm_opts, default=utm_opts)
else:
    st.info(f"No column “{utm_col}” — UTM filter hidden")
    sel_utm = None

# Price option filter
if price_col in df_raw.columns:
    price_opts = sorted(df_raw[price_col].dropna().unique())
    sel_price  = st.multiselect("Price option", price_opts, default=price_opts)
else:
    st.info(f"No column “{price_col}” — price filter hidden")
    sel_price = None

# ───────────────────────── 2. FILTER DATA ───────────────────
df = df_raw[
    (df_raw["real_payment"] == 1) &
    (df_raw["created_at"].dt.date.between(start, end))
].copy()

if sel_utm   is not None: df = df[df[utm_col].isin(sel_utm)]
if sel_price is not None: df = df[df[price_col].isin(sel_price)]

# ───────────────────────── 3. COHORT PREP ───────────────────
df["cohort_date"] = (
    df["created_at"].dt.to_period("W").apply(lambda r: r.start_time.date())
    if weekly else df["created_at"].dt.date
)

exp = (df.loc[df.index.repeat(df["charges_count"])]
         .assign(period=lambda d: d.groupby(level=0).cumcount()))

size = exp[exp.period == 0].groupby("cohort_date").size()

dead = (df[df["next_charge_date"].isna()]
        .groupby("cohort_date").size()
        .reindex(size.index, fill_value=0))
death_pct = (dead / size * 100).round(1)

ltv = (df.groupby("cohort_date")["send_event_amount"].sum()
         .reindex(size.index, fill_value=0) / size).round(2)

pivot = exp.pivot_table(index="cohort_date", columns="period",
                        aggfunc="size", fill_value=0)
ret   = pivot.div(size, axis=0).mul(100).round(1)
pivot.columns = ret.columns = [f"Period {p}" for p in pivot.columns]

# ───────────────────────── 4. TABLE DATA ────────────────────
def bar(p,w=10): return "🟥"*int(round(p/10)) + "⬜"*(w-int(round(p/10)))
death_cell = ("💀 "+death_pct.map(lambda v:f'{v:.1f}%')+" "
              + death_pct.map(bar)+"<br>("+dead.astype(str)+")")

combo = ret.astype(str)+"%<br>("+pivot.astype(str)+")"
combo.insert(0, "Cohort death", death_cell)
combo["LTV USD"] = ltv.map(lambda v:f'${v:,.2f}')
combo = combo.sort_index(ascending=False)

# colours
Y_R,Y_G,Y_B=255,212,0; BASE="#202020"; A0,A1=.2,.8
rgba = lambda a:f'rgba({Y_R},{Y_G},{Y_B},{a:.2f})'
txt  = lambda a:"black" if a>0.5 else "white"

header=["Cohort"]+combo.columns.tolist()
rows,fills,fonts=[],[],[]
for ix,row in combo.iterrows():
    rows.append([str(ix)]+row.tolist())
    c,f=["#1e1e1e","#333333"],["white","white"]
    for p in ret.loc[ix].values/100:
        if p==0 or pd.isna(p): c.append(BASE); f.append("white")
        else: a=A0+(A1-A0)*p; c.append(rgba(a)); f.append(txt(a))
    c.append("#333333"); f.append("white")               # LTV
    fills.append(c); fonts.append(f)

vals=list(map(list,zip(*rows)))
fills=list(map(list,zip(*fills)))
fonts=list(map(list,zip(*fonts)))

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

# ───────────────────── 5. LINE CHART (UTM) ──────────────────
new_subs = (exp[exp.period==0]
            .groupby(["cohort_date", utm_col]).size()
            .reset_index(name="New subs"))

fig_line = px.line(new_subs, x="cohort_date", y="New subs",
                   color=utm_col, markers=True,
                   title="New subscriptions by UTM source",
                   labels={"cohort_date":"Cohort", utm_col:"UTM source"})
fig_line.update_layout(margin=dict(l=10,r=10,t=40,b=50),
                       legend=dict(orientation="h", y=-0.25),
                       paper_bgcolor="#0f0f0f", plot_bgcolor="#0f0f0f")
st.plotly_chart(fig_line, use_container_width=True)

# ───────────────────── 6. CHOROPLETH (COUNTRY) ──────────────
import plotly.graph_objects as go

geo_df = (exp[exp.period == 0]                # только новые подписки
          .groupby(country_col).size()
          .reset_index(name="New subs"))

geo_df = geo_df[geo_df["New subs"] > 0]       # убираем страны с 0

fig_geo = go.Figure(go.Choropleth(
    locations   = geo_df[country_col],        # ISO-2 коды
    z           = geo_df["New subs"],
    locationmode= "ISO-2",
    colorscale  = "Blues",
    marker_line_color = "white",
    colorbar_title = "New subs"
))
fig_geo.update_layout(
    title_text = "New subscriptions by country",
    margin     = dict(l=10, r=10, t=40, b=10),
    geo        = dict(projection_type="natural earth",
                      bgcolor="#0f0f0f"),
    paper_bgcolor = "#0f0f0f",
    plot_bgcolor  = "#0f0f0f"
)

st.plotly_chart(fig_geo, use_container_width=True)

