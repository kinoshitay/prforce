"""
広報力測定ダッシュボード - メインページ（ランキング）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import glob
import os
from pathlib import Path
from dataclasses import asdict

from scorer import score_company, PRScore

st.set_page_config(
    page_title="広報力測定ダッシュボード",
    page_icon="📣",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path("data")
IS_CLOUD = bool(os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_SERVER_HEADLESS"))


# ──────────────────────────────────────────
# データ読み込み・スコアリング
# ──────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="データを読み込んでいます...")
def load_all_scores() -> tuple[list[dict], str]:
    """全企業のCSVを読み込んでスコアリングし、(スコアリスト, 最終更新日) を返す"""
    with open("companies.json", encoding="utf-8") as f:
        companies = json.load(f)

    scores = []
    latest_date = ""

    for co in companies:
        cid = co["company_id"]
        csvs = sorted(DATA_DIR.glob(f"releases_{cid}_*.csv"))
        if not csvs:
            continue
        df = pd.read_csv(csvs[-1])
        if df.empty:
            continue
        score = score_company(df)
        score.company_name = co["name"]
        d = asdict(score)
        d["category"] = co.get("category", "")
        scores.append(d)

        # 最終更新日を取得（ファイル名から）
        fname = csvs[-1].stem  # "releases_36528_20260320"
        date_part = fname.split("_")[-1]  # "20260320"
        if date_part > latest_date:
            latest_date = date_part

    scores.sort(key=lambda x: x["total_score"], reverse=True)
    return scores, latest_date


def format_date(d: str) -> str:
    if len(d) == 8:
        return f"{d[:4]}/{d[4:6]}/{d[6:]}"
    return d


# ──────────────────────────────────────────
# UI
# ──────────────────────────────────────────

st.title("📣 広報力測定ダッシュボード")
st.caption("PR Timesのプレスリリースデータをもとに、スタートアップの広報力を定量スコアリング")

scores, latest_date = load_all_scores()

if not scores:
    st.error("データが見つかりません。`batch_score.py` を実行してデータを収集してください。")
    st.stop()

# ── ヘッダー指標 ──────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("対象企業数", f"{len(scores)} 社")
with col2:
    total_releases = sum(s["total_releases"] for s in scores)
    st.metric("総リリース件数", f"{total_releases:,} 件")
with col3:
    avg_score = sum(s["total_score"] for s in scores) / len(scores)
    st.metric("平均スコア", f"{avg_score:.1f} / 100")
with col4:
    st.metric("データ更新日", format_date(latest_date))

st.divider()

# ── ランキングテーブル ──────────────────────
st.subheader("🏆 広報力ランキング")

GRADE_COLOR = {"S": "🥇", "A": "🥈", "B": "🥉", "C": "4️⃣", "D": "5️⃣"}

rows = []
for i, s in enumerate(scores, 1):
    q = s["volume_score"] + s["recent_activity_score"]
    qual = s["category_mix_score"] + s["consistency_score"] + s["growth_trajectory_score"]
    rows.append({
        "順位": i,
        "企業名": s["company_name"],
        "カテゴリ": s["category"],
        "総合スコア": s["total_score"],
        "グレード": f"{GRADE_COLOR.get(s['grade'], '')} {s['grade']}",
        "量 (30)": round(q, 1),
        "質 (40)": round(qual, 1),
        "影響力 (30)": s["impact_score"],
        "リリース数": s["total_releases"],
    })

df_rank = pd.DataFrame(rows)

st.dataframe(
    df_rank,
    use_container_width=True,
    hide_index=True,
    column_config={
        "総合スコア": st.column_config.ProgressColumn(
            "総合スコア", min_value=0, max_value=100, format="%.1f"
        ),
        "量 (30)": st.column_config.ProgressColumn(
            "量 (30)", min_value=0, max_value=30, format="%.1f"
        ),
        "質 (40)": st.column_config.ProgressColumn(
            "質 (40)", min_value=0, max_value=40, format="%.1f"
        ),
        "影響力 (30)": st.column_config.ProgressColumn(
            "影響力 (30)", min_value=0, max_value=30, format="%.1f"
        ),
    },
)

# ── レーダーチャート ────────────────────────
st.subheader("📊 スコア構成比較（レーダーチャート）")

categories = ["配信量", "継続活動", "カテゴリミックス", "継続安定性", "成長トレンド", "影響力"]

fig = go.Figure()
colors = ["#4F8BF9", "#FF6B6B", "#FFD93D", "#6BCB77", "#FF922B", "#DA77F2", "#74C0FC", "#A9E34B", "#FFA8A8"]

for idx, s in enumerate(scores):
    vals = [
        s["volume_score"] / 20 * 100,
        s["recent_activity_score"] / 10 * 100,
        s["category_mix_score"] / 15 * 100,
        s["consistency_score"] / 10 * 100,
        s["growth_trajectory_score"] / 15 * 100,
        s["impact_score"] / 30 * 100,
    ]
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]],
        theta=categories + [categories[0]],
        fill="toself",
        name=s["company_name"],
        line_color=colors[idx % len(colors)],
        opacity=0.6,
    ))

fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    showlegend=True,
    height=500,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
)
st.plotly_chart(fig, use_container_width=True)

# ── スコア棒グラフ ───────────────────────────
st.subheader("📈 総合スコア比較")

fig2 = go.Figure()
names = [s["company_name"] for s in scores]

for label, key, color in [
    ("量スコア", lambda s: s["volume_score"] + s["recent_activity_score"], "#4F8BF9"),
    ("質スコア", lambda s: s["category_mix_score"] + s["consistency_score"] + s["growth_trajectory_score"], "#6BCB77"),
    ("影響力スコア", lambda s: s["impact_score"], "#FF6B6B"),
]:
    fig2.add_trace(go.Bar(
        name=label,
        x=names,
        y=[key(s) for s in scores],
        marker_color=color,
    ))

fig2.update_layout(
    barmode="stack",
    height=400,
    xaxis_tickangle=-30,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    yaxis_title="スコア (0-100)",
)
st.plotly_chart(fig2, use_container_width=True)

# ── ダウンロード ────────────────────────────
st.divider()
col_dl1, col_dl2 = st.columns([1, 4])
with col_dl1:
    csv_bytes = df_rank.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 ランキングCSVをダウンロード",
        data=csv_bytes,
        file_name=f"pr_ranking_{latest_date}.csv",
        mime="text/csv",
    )

# ── データ更新（ローカル専用） ─────────────────
if not IS_CLOUD:
    st.divider()
    st.subheader("🔄 データ更新（ローカル限定）")
    st.caption("PR Timesから最新データを再取得します（企業ごとに1〜3分かかります）")

    with st.expander("更新設定"):
        max_clicks = st.slider("「もっと見る」最大クリック数", 5, 30, 15)
        force_update = st.checkbox("既存データを上書きして再取得", value=False)

    if st.button("⬇️ 全企業データを更新", type="primary"):
        import asyncio
        from scraper import fetch_releases
        from dataclasses import asdict as dc_asdict

        with open("companies.json", encoding="utf-8") as f:
            companies = json.load(f)

        progress = st.progress(0)
        status = st.empty()
        DATA_DIR.mkdir(exist_ok=True)

        async def update_all():
            for i, co in enumerate(companies):
                cid = co["company_id"]
                name = co["name"]
                if not force_update:
                    existing = sorted(DATA_DIR.glob(f"releases_{cid}_*.csv"))
                    if existing:
                        status.info(f"✅ {name}: スキップ（既存データあり）")
                        progress.progress((i + 1) / len(companies))
                        continue
                status.info(f"⬇️ {name} を取得中...")
                releases = await fetch_releases(cid, max_clicks=max_clicks)
                if releases:
                    df = pd.DataFrame([dc_asdict(r) for r in releases])
                    df = df.drop_duplicates(subset=["url"]).reset_index(drop=True)
                    from datetime import datetime
                    out = DATA_DIR / f"releases_{cid}_{datetime.now().strftime('%Y%m%d')}.csv"
                    df.to_csv(out, index=False, encoding="utf-8-sig")
                    status.success(f"✅ {name}: {len(df)} 件保存")
                progress.progress((i + 1) / len(companies))

        asyncio.run(update_all())
        st.cache_data.clear()
        st.success("更新完了！ページをリロードしてください。")
        st.rerun()

# ── フッター ────────────────────────────────
st.divider()
st.caption(
    "データソース: PR Times | スコア算出: 量(30点) + 質(40点) + 影響力(30点) | "
    "詳細は「企業詳細」「比較分析」ページへ"
)
