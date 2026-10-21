import os
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

st.set_page_config(page_title="Customer Segmentation Dashboard", page_icon="📊", layout="wide")
st.title("📊 Customer Segmentation Dashboard")
st.caption("Home Credit — клиенттердің құндылығы мен тәуекелін талдау")

def norm(s):
    return str(s).strip().lower().replace(" ", "_")

def find_col(columns, candidates):
    lookup = {norm(c): c for c in columns}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    for c in columns:
        nc = norm(c)
        if any(candidate in nc for candidate in candidates):
            return c
    return None

def load_from_postgres():
    with st.sidebar:
        st.subheader("PostgreSQL қосылымы")
        host = st.text_input("Host", value=os.getenv("PGHOST", "localhost"))
        port = st.text_input("Port", value=os.getenv("PGPORT", "5432"))
        database = st.text_input("Database", value=os.getenv("PGDATABASE", "customer_analytics"))
        user = st.text_input("User", value=os.getenv("PGUSER", "postgres"))
        password = st.text_input("Password", value=os.getenv("PGPASSWORD", ""), type="password")

    if not password:
        st.info("PostgreSQL паролін сол жақ панельге енгіз немесе CSV файлды жүкте.")
        return None

    try:
        url = URL.create(
            "postgresql+psycopg2",
            username=user, password=password, host=host,
            port=int(port), database=database
        )
        engine = create_engine(url)

        # Үш кестені клиент ID арқылы біріктіреміз.
        query = text("""
            SELECT
                cm."SK_ID_CURR",
                cs.customer_segment,
                cs.monetary_score,
                cs.frequency_score,
                cs.recency_score,
                cs.risk_score,
                cs.total_score,
                a."CODE_GENDER",
                a."NAME_FAMILY_STATUS",
                a."NAME_EDUCATION_TYPE",
                a."NAME_HOUSING_TYPE",
                a."OCCUPATION_TYPE",
                a."NAME_INCOME_TYPE",
                a."ORGANIZATION_TYPE",
                a."REGION_RATING_CLIENT",
                a."REGION_POPULATION_RELATIVE",
                a."FLAG_OWN_CAR",
                a."FLAG_OWN_REALTY",
                a."REG_CITY_NOT_LIVE_CITY",
                a."REG_CITY_NOT_WORK_CITY",
                a."LIVE_CITY_NOT_WORK_CITY",
                a."AMT_INCOME_TOTAL",
                a."AMT_CREDIT",
                a."TARGET",
                cm.monetary_value,
                cm.frequency,
                cm.average_loan_size,
                cm.payment_count,
                cm.recency_days,
                cm.credit_count,
                cm.overdue_over_30_count,
                cm.max_overdue_days,
                cm.overdue_over_30_pct,
                cm.approved_credit_total,
                cm.average_annuity
            FROM public.customer_metrics AS cm
            JOIN public.customer_segments AS cs
                ON cm."SK_ID_CURR" = cs."SK_ID_CURR"
            JOIN public.application_train AS a
                ON cm."SK_ID_CURR" = a."SK_ID_CURR"
        """)

        with engine.connect() as conn:
            df = pd.read_sql(query, conn)

        st.sidebar.success(f"Үш кесте біріктірілді. Клиент саны: {len(df):,}")
        return df

    except Exception as e:
        st.error("PostgreSQL-ге қосылу немесе үш кестені біріктіру сәтсіз аяқталды.")
        st.warning(
            "public схемасында customer_metrics, customer_segments және "
            "application_train кестелері бар екенін, баған атауларын және "
            "қосылым деректерін тексер."
        )
        st.code(str(e))
        return None

source = st.sidebar.radio("Дерек көзі", ["PostgreSQL", "CSV файл"])
df = None
if source == "CSV файл":
    uploaded = st.sidebar.file_uploader("Дайын қорытынды кестені CSV ретінде жүкте", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
        except Exception as e:
            st.error(f"CSV оқу қатесі: {e}")
else:
    df = load_from_postgres()

if df is None:
    st.markdown("""
    ### Қалай бастау керек
    1. PostgreSQL режимінде қосылым деректерін енгіз — бағдарлама customer_metrics, customer_segments және application_train кестелерін автоматты біріктіреді.
    2. Немесе CSV файл режимінде дайын қорытынды CSV файлын жүкте.
    3. Демографиялық, тұрғын үй, жұмыс және өңірлік графиктер үшін CSV файлында тиісті бағандар болуы керек. Толық талдау үшін PostgreSQL режимін қолданған дұрыс.

    Бұл dashboard деректерді өзгертпейді — тек оқып, график сызады.
    """)
    st.stop()

if df.empty:
    st.warning("Таңдалған кестеде жол жоқ.")
    st.stop()

df.columns = [str(c) for c in df.columns]
segment_col = find_col(df.columns, ["customer_segment", "segment", "segment_name", "customer_group"])
client_col = find_col(df.columns, ["sk_id_curr", "customer_id", "client_id"])
monetary_col = find_col(df.columns, ["monetary_value", "total_amount", "total_spent"])
frequency_col = find_col(df.columns, ["frequency", "application_count", "credit_count"])
avg_loan_col = find_col(df.columns, ["average_loan_size", "avg_loan_size", "avg_loan", "average_credit"])
recency_col = find_col(df.columns, ["recency_days", "recency"])
overdue_col = find_col(df.columns, ["overdue_over_30_count", "overdue_count", "late_payment_count"])
max_overdue_col = find_col(df.columns, ["max_overdue_days", "max_dpd"])

df[segment_col] = df[segment_col].fillna("Unknown Risk").astype(str)
segments = sorted(df[segment_col].unique().tolist())
with st.sidebar:
    st.subheader("Фильтр")
    selected_segments = st.multiselect("Клиент сегменті", segments, default=segments)
filtered = df[df[segment_col].isin(selected_segments)].copy()
if filtered.empty:
    st.warning("Фильтр бойынша клиент табылмады.")
    st.stop()

def mean_or_na(col):
    return pd.to_numeric(filtered[col], errors="coerce").mean() if col else None

def fmt(value):
    return "N/A" if value is None or pd.isna(value) else f"{value:,.2f}"

k1, k2, k3, k4 = st.columns(4)
k1.metric("Клиенттер саны", f"{len(filtered):,}")
k2.metric("Орташа Monetary Value", fmt(mean_or_na(monetary_col)))
k3.metric("Орташа несие көлемі", fmt(mean_or_na(avg_loan_col)))
k4.metric("Орташа Frequency", fmt(mean_or_na(frequency_col)))

st.divider()
left, right = st.columns(2)

with left:
    count_df = filtered.groupby(segment_col).size().reset_index(name="customers").sort_values("customers", ascending=False)
    fig = px.bar(count_df, x=segment_col, y="customers", color=segment_col,
                 title="Сегменттер бойынша клиенттер саны",
                 labels={segment_col: "Сегмент", "customers": "Клиенттер саны"},
                 text="customers")
    fig.update_layout(showlegend=False, xaxis_tickangle=-25)
    st.plotly_chart(fig, use_container_width=True)

with right:
    if monetary_col:
        work = filtered.copy()
        work[monetary_col] = pd.to_numeric(work[monetary_col], errors="coerce")
        money_df = work.groupby(segment_col, dropna=False)[monetary_col].mean().reset_index()
        money_df.columns = ["Сегмент", "Орташа Monetary Value"]
        fig = px.bar(money_df, x="Сегмент", y="Орташа Monetary Value", color="Сегмент",
                     title="Сегмент бойынша орташа қаржылық көлем")
        fig.update_layout(showlegend=False, xaxis_tickangle=-25)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Monetary Value бағаны табылмады. Кестеде бар бағандарды төменнен тексер.")

left, right = st.columns(2)
with left:
    if frequency_col and avg_loan_col:
        work = filtered.copy()
        work[frequency_col] = pd.to_numeric(work[frequency_col], errors="coerce")
        work[avg_loan_col] = pd.to_numeric(work[avg_loan_col], errors="coerce")
        freq_df = work.groupby(segment_col)[[frequency_col, avg_loan_col]].mean().reset_index()
        fig = px.scatter(freq_df, x=frequency_col, y=avg_loan_col, text=segment_col,
                         title="Frequency және орташа несие көлемі",
                         labels={frequency_col: "Орташа Frequency", avg_loan_col: "Орташа несие көлемі"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Frequency немесе average_loan_size бағаны табылмады.")

with right:
    risk_names = [s for s in segments if "risk" in s.lower() or "unknown" in s.lower()]
    risk_df = count_df[count_df[segment_col].isin(risk_names)]
    if not risk_df.empty:
        fig = px.pie(risk_df, names=segment_col, values="customers", hole=0.45,
                     title="Тәуекелге қатысты сегменттер үлесі")
        st.plotly_chart(fig, use_container_width=True)
    elif overdue_col or max_overdue_col:
        risk_metric = overdue_col or max_overdue_col
        vals = pd.to_numeric(filtered[risk_metric], errors="coerce").fillna(0)
        risk_count = int((vals > 0).sum())
        st.metric("Тәуекел көрсеткіші нөлден жоғары клиенттер", f"{risk_count:,}")
    else:
        st.info("Тәуекел бағандары жоқ; сегменттер атауы бойынша Unknown Risk/High Risk топтары ізделді.")

st.subheader("Сегменттердің салыстырмалы кестесі")
agg = {}
if client_col:
    agg[client_col] = "count"
if monetary_col:
    agg[monetary_col] = "mean"
if frequency_col:
    agg[frequency_col] = "mean"
if avg_loan_col:
    agg[avg_loan_col] = "mean"
if recency_col:
    agg[recency_col] = "mean"
if overdue_col:
    agg[overdue_col] = "sum"
if agg:
    summary = filtered.groupby(segment_col).agg(agg).reset_index()
    rename = {client_col: "Жол саны", monetary_col: "Орташа Monetary Value",
              frequency_col: "Орташа Frequency", avg_loan_col: "Орташа несие көлемі",
              recency_col: "Орташа Recency (күн)", overdue_col: "30 күннен көп кешігу саны"}
    summary = summary.rename(columns={k: v for k, v in rename.items() if k and k in summary.columns})
    st.dataframe(summary, use_container_width=True, hide_index=True)
else:
    st.info("Салыстыруға арналған сандық бағандар автоматты түрде анықталмады.")


st.divider()
st.header("Клиенттердің демографиялық және әлеуметтік профилі")

# Аналитикалық тұрғыдан: демография бөлек, тұрғын үй/табыс/мүлік бөлек көрсетіледі.
# Жыныс, отбасы, білім — жинақталған бағандар; тұрғын үй мен табыс көзі — сегмент ішіндегі donut;
# мүлік/автокөлік — топталған бағандар. Осылай барлық график бірдей болмайды.

core_dimensions = [
    ("CODE_GENDER", "Жыныс"),
    ("NAME_FAMILY_STATUS", "Отбасылық жағдай"),
    ("NAME_EDUCATION_TYPE", "Білім деңгейі"),
]

social_dimensions = [
    ("NAME_HOUSING_TYPE", "Тұрғын үй түрі"),
    ("NAME_INCOME_TYPE", "Табыс көзі"),
]

ownership_dimensions = [
    ("FLAG_OWN_REALTY", "Жылжымайтын мүлік иеленуі"),
    ("FLAG_OWN_CAR", "Автокөлік иеленуі"),
]

def display_category(value, mapping):
    return mapping.get(str(value), str(value))

# 1. Негізгі демография: үш бөлек, жинақталған бағанды график.
st.subheader("1. Негізгі демография")
for col, title in core_dimensions:
    if col not in filtered.columns:
        continue
    data = filtered.dropna(subset=[col, segment_col]).copy()
    if data.empty:
        continue

    data[col] = data[col].astype(str)
    grouped = (
        data.groupby([segment_col, col], dropna=False)
        .size().reset_index(name="Клиенттер саны")
    )
    grouped["Үлес (%)"] = (
        grouped["Клиенттер саны"]
        / grouped.groupby(segment_col)["Клиенттер саны"].transform("sum") * 100
    )
    fig = px.bar(
        grouped,
        x=segment_col,
        y="Үлес (%)",
        color=col,
        barmode="stack",
        title=f"{title}: әр сегмент ішіндегі үлесі",
        labels={segment_col: "Клиент сегменті", col: title, "Үлес (%)": "Үлес (%)"},
        hover_data={"Клиенттер саны": True, "Үлес (%)": ":.1f"}
    )
    fig.update_layout(yaxis_range=[0, 100], xaxis_tickangle=-18, legend_title_text=title)
    st.plotly_chart(fig, use_container_width=True)
    with st.expander(f"{title}: толық кесте"):
        st.dataframe(grouped.round(2), use_container_width=True, hide_index=True)

# 2. Әлеуметтік/экономикалық сипаттамалар: әр сегментке жеке donut,
# бірақ әр көрсеткіш үшін бір қатарда бірнеше кішкентай график жасау орнына,
# сегментті selectbox арқылы таңдау — интерфейсті ықшам ұстайды.
st.subheader("2. Тұрғын үй және табыс көзі")
segment_options = sorted(filtered[segment_col].dropna().astype(str).unique().tolist())
selected_profile_segment = st.selectbox(
    "Дөңгелек диаграммалар үшін сегментті таңда",
    segment_options,
    key="profile_segment_selector"
)
profile_data = filtered[filtered[segment_col].astype(str) == selected_profile_segment].copy()

social_cols = st.columns(2)
for i, (col, title) in enumerate(social_dimensions):
    with social_cols[i]:
        if col not in profile_data.columns:
            st.info(f"{title}: баған табылмады.")
            continue
        data = profile_data.dropna(subset=[col]).copy()
        if data.empty:
            st.info(f"{title}: дерек жоқ.")
            continue
        counts = data[col].astype(str).value_counts().rename_axis("Санат").reset_index(name="Клиенттер саны")
        # Санаттары өте көп болса, ең үлкен 7 санат + Басқа; шағын диаграмма анық көрінеді.
        if len(counts) > 8:
            top = counts.head(7).copy()
            other_count = int(counts.iloc[7:]["Клиенттер саны"].sum())
            counts = pd.concat(
                [top, pd.DataFrame([{"Санат": "Басқа санаттар", "Клиенттер саны": other_count}])],
                ignore_index=True
            )
        fig = px.pie(
            counts, names="Санат", values="Клиенттер саны", hole=0.42,
            title=f"{title} — {selected_profile_segment}"
        )
        fig.update_traces(
            textposition="inside", textinfo="percent",
            hovertemplate="%{label}<br>Клиенттер: %{value:,}<br>Үлес: %{percent}<extra></extra>"
        )
        fig.update_layout(height=390, margin=dict(l=8, r=8, t=60, b=8), legend_title_text=title)
        st.plotly_chart(fig, use_container_width=True, key=f"profile_{col}")

# 3. Меншік көрсеткіштері: grouped bars — Y/N-ді сегменттер арасында салыстыру.
st.subheader("3. Автокөлік және жылжымайтын мүлік")
ownership_cols = st.columns(2)
for i, (col, title) in enumerate(ownership_dimensions):
    with ownership_cols[i]:
        if col not in filtered.columns:
            st.info(f"{title}: баған табылмады.")
            continue
        data = filtered.dropna(subset=[col, segment_col]).copy()
        if data.empty:
            st.info(f"{title}: дерек жоқ.")
            continue
        data[col] = data[col].astype(str).replace({"Y": "Иә", "N": "Жоқ"})
        grouped = (
            data.groupby([segment_col, col], dropna=False)
            .size().reset_index(name="Клиенттер саны")
        )
        fig = px.bar(
            grouped, x=segment_col, y="Клиенттер саны", color=col, barmode="group",
            title=f"{title} — сегменттер бойынша",
            labels={segment_col: "Клиент сегменті", col: title, "Клиенттер саны": "Клиенттер саны"},
            text="Клиенттер саны"
        )
        fig.update_layout(xaxis_tickangle=-20, legend_title_text=title)
        st.plotly_chart(fig, use_container_width=True)

# 4. Қысқа, дерекке сүйенген қорытынды.
st.subheader("4. Қорытынды")
st.markdown(
    "Төмендегі автоматты қорытынды ағымдағы сүзгідегі деректердің ең жиі кездесетін "
    "санаттарын көрсетеді. Бұл байланыстар сипаттамалық болып табылады, себеп-салдарды дәлелдемейді."
)
conclusion_lines = []
for col, title in core_dimensions + social_dimensions + ownership_dimensions:
    if col not in filtered.columns:
        continue
    vals = filtered[col].dropna().astype(str).value_counts()
    total = int(vals.sum())
    if total and not vals.empty:
        top_category = vals.index[0]
        top_percent = vals.iloc[0] / total * 100
        conclusion_lines.append(
            f"- **{title}:** ең жиі кездесетін санат — **{top_category}** "
            f"({top_percent:.1f}%, {int(vals.iloc[0]):,} клиент)."
        )
if conclusion_lines:
    st.markdown("\n".join(conclusion_lines))
else:
    st.info("Қорытынды жасауға жеткілікті дерек жоқ.")

st.caption(
    "TARGET = 1 — бастапқы деректерде төлем қиындықтары тіркелгенін білдіреді. "
    "Бұл барлық несиенің дефолты дегенді білдірмейді. Нақты қала атауы бұл кестеде жоқ."
)

with st.expander("Деректерді тексеру"):
    st.write(f"Жол саны: {len(df):,} | Баған саны: {len(df.columns)}")
    st.write("Анықталған бағандар:")
    st.json({
        "segment": segment_col, "client_id": client_col, "monetary_value": monetary_col,
        "frequency": frequency_col, "average_loan_size": avg_loan_col,
        "recency_days": recency_col, "overdue_over_30_count": overdue_col,
        "max_overdue_days": max_overdue_col
    })
    st.dataframe(filtered.head(100), use_container_width=True, hide_index=True)

csv = filtered.to_csv(index=False).encode("utf-8-sig")
st.download_button("📥 Қазіргі сүзілген деректерді CSV жүктеу", data=csv,
                   file_name="customer_segmentation_filtered.csv", mime="text/csv")
