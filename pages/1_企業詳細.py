"""
広報力測定ダッシュボード - 企業詳細ページ
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import glob
from typing import Optional
from pathlib import Path
from dataclasses import asdict

from scorer import score_company, infer_category

st.set_page_config(
    page_title="企業詳細 | 広報力測定",
    page_icon="🔍",
    layout="wide",
)

DATA_DIR = Path("data")

GRADE_COLORS = {"S": "#FFD700", "A": "#4F8BF9", "B": "#6BCB77", "C": "#FFD93D", "D": "#FF6B6B"}


@st.cache_data(ttl=3600)
def load_company_data(company_id: str) -> Optional[pd.DataFrame]:
    csvs = sorted(DATA_DIR.glob(f"releases_{company_id}_*.csv"))
    if not csvs:
        return None
    df = pd.read_csv(csvs[-1])
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df = df.dropna(subset=["published_at"]).sort_values("published_at", ascending=False)
    df["category"] = df["title"].apply(infer_category)
    df["year_month"] = df["published_at"].dt.to_period("M").astype(str)
    return df


@st.cache_data(ttl=3600)
def load_companies() -> list[dict]:
    with open("companies.json", encoding="utf-8") as f:
        return json.load(f)


# ── サイドバー ──────────────────────────────
companies = load_companies()
company_names = [co["name"] for co in companies]

st.sidebar.title("🔍 企業詳細")
selected_name = st.sidebar.selectbox("企業を選択", company_names)
selected = next(co for co in companies if co["name"] == selected_name)

# ── データ読み込み ──────────────────────────
df = load_company_data(selected["company_id"])

if df is None or df.empty:
    st.error(f"**{selected_name}** のデータが見つかりません。")
    st.stop()

score = score_company(df)
score.company_name = selected_name

# ── ヘッダー ───────────────────────────────
st.title(f"📣 {selected_name}")
st.caption(f"カテゴリ: {selected.get('category', '—')}　|　company_id: {selected['company_id']}")

grade_color = GRADE_COLORS.get(score.grade, "#FFFFFF")

col_score, col_grade, col_releases, col_period = st.columns(4)
with col_score:
    st.metric("総合スコア", f"{score.total_score:.1f} / 100")
with col_grade:
    st.markdown(f"<h2 style='color:{grade_color}; margin:0'>グレード {score.grade}</h2>", unsafe_allow_html=True)
with col_releases:
    st.metric("総リリース件数", f"{score.total_releases:,} 件")
with col_period:
    st.metric("対象期間", f"{score.date_from} 〜 {score.date_to}")

st.divider()

# ── スコア内訳 ─────────────────────────────
st.subheader("📊 スコア内訳")

score_items = [
    ("配信量",           score.volume_score,             20,  "#4F8BF9"),
    ("継続活動",         score.recent_activity_score,    10,  "#74C0FC"),
    ("カテゴリミックス", score.category_mix_score,       15,  "#6BCB77"),
    ("継続安定性",       score.consistency_score,        10,  "#A9E34B"),
    ("成長トレンド",     score.growth_trajectory_score,  15,  "#FFD93D"),
    ("インパクト",       score.impact_score,             30,  "#FF6B6B"),
]

fig_score = go.Figure()
labels = [f"{name}<br>({v:.1f}/{m})" for name, v, m, _ in score_items]
values = [v / m * 100 for _, v, m, _ in score_items]
colors_list = [c for _, _, _, c in score_items]

fig_score.add_trace(go.Bar(
    x=values,
    y=labels,
    orientation="h",
    marker_color=colors_list,
    text=[f"{v:.1f}/{m}pt" for _, v, m, _ in score_items],
    textposition="outside",
))
fig_score.update_layout(
    xaxis=dict(title="達成率 (%)", range=[0, 120]),
    height=350,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    margin=dict(l=180),
)
st.plotly_chart(fig_score, use_container_width=True)

# ── 月別リリース推移 ───────────────────────
st.subheader("📅 月別リリース件数推移")

monthly = df.groupby("year_month").size().reset_index(name="count")
monthly = monthly.sort_values("year_month")

fig_monthly = go.Figure()
fig_monthly.add_trace(go.Bar(
    x=monthly["year_month"],
    y=monthly["count"],
    marker_color="#4F8BF9",
    name="リリース件数",
))
# 3ヶ月移動平均
if len(monthly) >= 3:
    monthly["ma3"] = monthly["count"].rolling(3, min_periods=1).mean()
    fig_monthly.add_trace(go.Scatter(
        x=monthly["year_month"],
        y=monthly["ma3"],
        mode="lines",
        name="3ヶ月移動平均",
        line=dict(color="#FFD93D", width=2),
    ))

fig_monthly.update_layout(
    height=350,
    xaxis_tickangle=-45,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    yaxis_title="件数",
)
st.plotly_chart(fig_monthly, use_container_width=True)

# ── カテゴリ分布 ───────────────────────────
col_pie, col_top = st.columns([1, 1])

with col_pie:
    st.subheader("🏷️ カテゴリ分布")
    cat_counts = df["category"].value_counts().reset_index()
    cat_counts.columns = ["カテゴリ", "件数"]

    fig_pie = px.pie(
        cat_counts,
        values="件数",
        names="カテゴリ",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Plotly,
    )
    fig_pie.update_layout(
        height=350,
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#FAFAFA",
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_top:
    st.subheader("⚡ 直近リリース（最新10件）")
    recent = df.head(10)[["published_at", "title", "category", "url"]].copy()
    recent["published_at"] = recent["published_at"].dt.strftime("%Y-%m-%d")
    recent["リンク"] = recent["url"].apply(lambda u: f"[🔗 開く]({u})" if u else "")

    st.dataframe(
        recent[["published_at", "title", "category", "リンク"]].rename(columns={
            "published_at": "日付",
            "title": "タイトル",
            "category": "カテゴリ",
        }),
        use_container_width=True,
        hide_index=True,
        column_config={"リンク": st.column_config.LinkColumn("リンク")},
    )

# ── 直近12ヶ月トレンド詳細 ──────────────────
st.divider()
st.subheader("📈 直近12ヶ月のリリース分析")

now = pd.Timestamp.now()
df_recent = df[df["published_at"] >= now - pd.DateOffset(months=12)].copy()
recent_monthly = df_recent.groupby("year_month").size().reset_index(name="count")
recent_monthly = recent_monthly.sort_values("year_month")

cat_monthly = (
    df_recent.groupby(["year_month", "category"]).size()
    .reset_index(name="count")
    .sort_values("year_month")
)

fig_stacked = px.bar(
    cat_monthly,
    x="year_month",
    y="count",
    color="category",
    title="直近12ヶ月 カテゴリ別リリース数",
    labels={"year_month": "年月", "count": "件数", "category": "カテゴリ"},
    color_discrete_sequence=px.colors.qualitative.Plotly,
)
fig_stacked.update_layout(
    height=350,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    xaxis_tickangle=-30,
)
st.plotly_chart(fig_stacked, use_container_width=True)

# ── 全リリース一覧 ────────────────────────
with st.expander(f"📋 全リリース一覧 ({len(df)} 件)"):
    all_df = df[["published_at", "title", "category", "url"]].copy()
    all_df["published_at"] = all_df["published_at"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        all_df.rename(columns={
            "published_at": "日付", "title": "タイトル",
            "category": "カテゴリ", "url": "URL",
        }),
        use_container_width=True,
        hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )
