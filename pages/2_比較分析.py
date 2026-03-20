"""
広報力測定ダッシュボード - 比較分析ページ
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from scorer import score_company, infer_category

st.set_page_config(
    page_title="比較分析 | 広報力測定",
    page_icon="⚖️",
    layout="wide",
)

DATA_DIR = Path("data")
COLORS = ["#4F8BF9", "#FF6B6B", "#6BCB77", "#FFD93D", "#DA77F2", "#FF922B", "#74C0FC", "#A9E34B"]


@st.cache_data(ttl=3600)
def load_companies() -> list[dict]:
    with open("companies.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=3600)
def load_df(company_id: str) -> Optional[pd.DataFrame]:
    csvs = sorted(DATA_DIR.glob(f"releases_{company_id}_*.csv"))
    if not csvs:
        return None
    df = pd.read_csv(csvs[-1])
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df = df.dropna(subset=["published_at"])
    df["category"] = df["title"].apply(infer_category)
    df["year_month"] = df["published_at"].dt.to_period("M").astype(str)
    return df


# ── サイドバー ──────────────────────────────
companies = load_companies()
all_names = [co["name"] for co in companies]

st.sidebar.title("⚖️ 比較分析")
st.sidebar.caption("2〜5社を選んで比較できます")
selected_names = st.sidebar.multiselect(
    "比較する企業を選択",
    all_names,
    default=all_names[:4],
    max_selections=5,
)

if len(selected_names) < 2:
    st.warning("2社以上を選択してください。")
    st.stop()

selected_companies = [co for co in companies if co["name"] in selected_names]

# ── データ読み込み ──────────────────────────
company_data = {}
company_scores = {}

for co in selected_companies:
    df = load_df(co["company_id"])
    if df is not None and not df.empty:
        score = score_company(df)
        score.company_name = co["name"]
        company_data[co["name"]] = df
        company_scores[co["name"]] = score

if not company_scores:
    st.error("選択した企業のデータが見つかりません。")
    st.stop()

names = list(company_scores.keys())
scores = list(company_scores.values())

# ── タイトル ───────────────────────────────
st.title(f"⚖️ 比較分析：{' vs '.join(names)}")

# ── 総合スコア比較メトリクス ────────────────
cols = st.columns(len(names))
for i, (name, score) in enumerate(zip(names, scores)):
    with cols[i]:
        grade_colors = {"S": "gold", "A": "#4F8BF9", "B": "#6BCB77", "C": "#FFD93D", "D": "#FF6B6B"}
        color = grade_colors.get(score.grade, "white")
        st.markdown(
            f"<div style='text-align:center; padding:10px; border-radius:8px; "
            f"border: 1px solid {color}'>"
            f"<h4 style='margin:0; color:{color}'>{name}</h4>"
            f"<h2 style='margin:4px 0; color:{color}'>{score.total_score:.1f}</h2>"
            f"<p style='margin:0; color:{color}'>グレード {score.grade}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ── スコア積上げ棒グラフ ────────────────────
st.subheader("📊 スコア内訳比較")

fig_stack = go.Figure()
for label, key, color in [
    ("量スコア (30pt)",  lambda s: s.volume_score + s.recent_activity_score,         "#4F8BF9"),
    ("質スコア (40pt)",  lambda s: s.category_mix_score + s.consistency_score + s.growth_trajectory_score, "#6BCB77"),
    ("影響力 (30pt)",   lambda s: s.impact_score,                                    "#FF6B6B"),
]:
    fig_stack.add_trace(go.Bar(
        name=label,
        x=names,
        y=[key(s) for s in scores],
        marker_color=color,
        text=[f"{key(s):.1f}" for s in scores],
        textposition="inside",
    ))

fig_stack.update_layout(
    barmode="stack",
    height=400,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    yaxis_title="スコア (0-100)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_stack, use_container_width=True)

# ── レーダーチャート ─────────────────────────
st.subheader("🕸️ スコア要素レーダー比較")

radar_cats = ["配信量", "継続活動", "カテゴリMix", "継続安定性", "成長トレンド", "影響力"]

fig_radar = go.Figure()
for i, (name, score) in enumerate(zip(names, scores)):
    vals = [
        score.volume_score / 20 * 100,
        score.recent_activity_score / 10 * 100,
        score.category_mix_score / 15 * 100,
        score.consistency_score / 10 * 100,
        score.growth_trajectory_score / 15 * 100,
        score.impact_score / 30 * 100,
    ]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals + [vals[0]],
        theta=radar_cats + [radar_cats[0]],
        fill="toself",
        name=name,
        line_color=COLORS[i % len(COLORS)],
        opacity=0.65,
    ))

fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    height=500,
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
)
st.plotly_chart(fig_radar, use_container_width=True)

# ── 月別リリース数推移比較 ──────────────────
st.subheader("📅 月別リリース数推移")

# 共通の月リストを作成
all_months = sorted(set(
    m for df in company_data.values() for m in df["year_month"].unique()
))

fig_trend = go.Figure()
for i, (name, df) in enumerate(company_data.items()):
    monthly = df.groupby("year_month").size().reindex(all_months, fill_value=0)
    # 3ヶ月移動平均
    ma = monthly.rolling(3, min_periods=1).mean()
    fig_trend.add_trace(go.Scatter(
        x=all_months,
        y=ma.values,
        mode="lines",
        name=name,
        line=dict(color=COLORS[i % len(COLORS)], width=2),
    ))

fig_trend.update_layout(
    height=400,
    xaxis_tickangle=-45,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    yaxis_title="件数（3ヶ月移動平均）",
    xaxis=dict(
        # 直近3年に絞ることができるよう範囲スライダー付き
        rangeslider=dict(visible=True),
        type="category",
    ),
)
st.plotly_chart(fig_trend, use_container_width=True)

# ── カテゴリ比較 ──────────────────────────
st.subheader("🏷️ カテゴリ分布比較")

cat_rows = []
for name, df in company_data.items():
    counts = df["category"].value_counts()
    total = len(df)
    for cat, cnt in counts.items():
        cat_rows.append({
            "企業名": name,
            "カテゴリ": cat,
            "件数": cnt,
            "割合 (%)": round(cnt / total * 100, 1),
        })

cat_df = pd.DataFrame(cat_rows)

fig_cat = px.bar(
    cat_df,
    x="企業名",
    y="割合 (%)",
    color="カテゴリ",
    barmode="stack",
    color_discrete_sequence=px.colors.qualitative.Plotly,
    height=400,
)
fig_cat.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
)
st.plotly_chart(fig_cat, use_container_width=True)

# ── 比較サマリーテーブル ───────────────────
st.subheader("📋 比較サマリー")

summary_rows = []
for name, score in company_scores.items():
    summary_rows.append({
        "企業名": name,
        "総合スコア": score.total_score,
        "グレード": score.grade,
        "量 (30)": round(score.volume_score + score.recent_activity_score, 1),
        "質 (40)": round(score.category_mix_score + score.consistency_score + score.growth_trajectory_score, 1),
        "影響力 (30)": score.impact_score,
        "件数": score.total_releases,
        "活動月数": score.active_months,
        "開始日": score.date_from,
    })

summary_df = pd.DataFrame(summary_rows)

st.dataframe(
    summary_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "総合スコア": st.column_config.ProgressColumn(
            "総合スコア", min_value=0, max_value=100, format="%.1f"
        ),
    },
)

# ダウンロード
csv_bytes = summary_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "📥 比較サマリーをCSVダウンロード",
    data=csv_bytes,
    file_name="pr_comparison.csv",
    mime="text/csv",
)
