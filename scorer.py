"""
広報力スコアリングエンジン
入力: releases_{company_id}_*.csv
出力: 各企業の広報力スコア（0〜100点）
"""

import pandas as pd
import numpy as np
import json
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional
import re
import glob


# ============================================================
# スコアリング設定
# ============================================================

# カテゴリ別リリースの重み（高インパクトなほど高い）
CATEGORY_WEIGHTS = {
    "資金調達": 3.0,
    "上場": 5.0,
    "M&A": 4.0,
    "新製品・新サービス": 2.0,
    "導入事例": 1.5,
    "パートナーシップ": 2.0,
    "採用": 1.0,
    "受賞・認定": 1.5,
    "その他": 1.0,
}

# タイトルからカテゴリを推定するキーワード
CATEGORY_KEYWORDS = {
    "資金調達": ["資金調達", "シリーズ", "億円調達", "ファンド", "投資"],
    "上場": ["IPO", "上場", "東証"],
    "M&A": ["買収", "M&A", "合併", "子会社化"],
    "新製品・新サービス": ["リリース", "提供開始", "ローンチ", "新機能", "β版", "正式リリース"],
    "導入事例": ["導入", "採用事例", "活用事例", "導入事例"],
    "パートナーシップ": ["提携", "パートナー", "連携", "協業"],
    "採用": ["採用", "募集", "入社", "新卒"],
    "受賞・認定": ["受賞", "表彰", "選定", "認定", "アワード"],
}


def infer_category(title: str) -> str:
    """タイトルからリリースカテゴリを推定"""
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return cat
    return "その他"


@dataclass
class PRScore:
    company_id: str
    company_name: str
    scored_at: str

    # --- 量スコア (30点満点) ---
    volume_score: float         # 配信頻度・総本数
    recent_activity_score: float  # 直近12ヶ月の活動量

    # --- 質スコア (40点満点) ---
    category_mix_score: float   # 重要カテゴリの割合
    consistency_score: float    # 配信の継続性（月ごとのばらつき）
    growth_trajectory_score: float  # 直近トレンド（伸び率）

    # --- 影響力スコア (30点満点) ※将来拡張 ---
    impact_score: float         # 現時点はカテゴリ重み合算で代替

    # --- 総合 ---
    total_score: float
    grade: str                  # S/A/B/C/D

    # メタ情報
    total_releases: int
    active_months: int
    date_from: str
    date_to: str
    top_categories: dict


def score_company(df: pd.DataFrame) -> PRScore:
    """DataFrameから広報力スコアを算出"""
    df = df.copy()
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df = df.dropna(subset=["published_at"]).sort_values("published_at")

    company_id = str(df["company_id"].iloc[0])
    company_name = str(df["company_name"].iloc[0]) if "company_name" in df.columns else company_id

    # カテゴリ推定
    df["category_inferred"] = df["title"].apply(infer_category)

    # 月次集計
    df["year_month"] = df["published_at"].dt.to_period("M")
    monthly = df.groupby("year_month").size()

    now = pd.Period(datetime.now(), freq="M")
    total = len(df)
    active_months = len(monthly)

    # ========== 量スコア (30点) ==========
    # 直近12ヶ月の配信本数
    recent_months = pd.period_range(end=now, periods=12, freq="M")
    recent_count = int(monthly[monthly.index.isin(recent_months)].sum())
    # 月平均10本以上で満点（ベンチマーク値）
    volume_score = min(recent_count / (10 * 12), 1.0) * 20

    # 配信継続率（直近12ヶ月で何ヶ月配信したか）
    recent_active = monthly[monthly.index.isin(recent_months)].count()
    recent_activity_score = (recent_active / 12) * 10

    # ========== 質スコア (40点) ==========
    # カテゴリミックス: 高インパクトカテゴリ（資金調達・新製品・提携）の割合
    high_impact_cats = {"資金調達", "M&A", "新製品・新サービス", "パートナーシップ", "上場"}
    high_impact_count = df[df["category_inferred"].isin(high_impact_cats)].shape[0]
    category_mix_score = min(high_impact_count / max(total, 1) / 0.4, 1.0) * 15

    # 継続性スコア: 月次配信の変動係数（CV）が低いほど高スコア
    if len(monthly) >= 3:
        cv = float(monthly.std() / monthly.mean()) if monthly.mean() > 0 else 1.0
        consistency_score = max(0.0, 1.0 - cv / 2.0) * 10
    else:
        consistency_score = 0.0

    # 成長トレンド: 直近6ヶ月 vs 前6ヶ月の比較
    recent6 = pd.period_range(end=now, periods=6, freq="M")
    prev6 = pd.period_range(end=now - 6, periods=6, freq="M")
    r6_count = int(monthly[monthly.index.isin(recent6)].sum())
    p6_count = int(monthly[monthly.index.isin(prev6)].sum())
    if p6_count > 0:
        growth_rate = r6_count / p6_count
        growth_trajectory_score = min(growth_rate / 1.5, 1.0) * 15
    else:
        growth_trajectory_score = 5.0  # データ不足時は中間値

    # ========== 影響力スコア (30点) ==========
    # カテゴリ重み合算（重要度の高いリリースが多いほど高スコア）
    weighted_sum = df["category_inferred"].map(CATEGORY_WEIGHTS).sum()
    max_possible = total * CATEGORY_WEIGHTS["新製品・新サービス"]  # 全部新製品だった場合
    impact_score = min(weighted_sum / max(max_possible, 1) / 0.6, 1.0) * 30

    # ========== 総合スコア ==========
    total_score = round(
        volume_score + recent_activity_score
        + category_mix_score + consistency_score + growth_trajectory_score
        + impact_score,
        1,
    )
    total_score = min(total_score, 100.0)

    # グレード判定
    grade = _to_grade(total_score)

    # カテゴリ分布
    top_categories = df["category_inferred"].value_counts().head(5).to_dict()

    return PRScore(
        company_id=company_id,
        company_name=company_name,
        scored_at=datetime.now().strftime("%Y-%m-%d"),
        volume_score=round(volume_score, 1),
        recent_activity_score=round(recent_activity_score, 1),
        category_mix_score=round(category_mix_score, 1),
        consistency_score=round(consistency_score, 1),
        growth_trajectory_score=round(growth_trajectory_score, 1),
        impact_score=round(impact_score, 1),
        total_score=total_score,
        grade=grade,
        total_releases=total,
        active_months=active_months,
        date_from=str(df["published_at"].min().date()),
        date_to=str(df["published_at"].max().date()),
        top_categories=top_categories,
    )


def _to_grade(score: float) -> str:
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def print_scorecard(s: PRScore):
    """スコアカードを見やすく表示"""
    bar = lambda v, max_v: "█" * int(v / max_v * 20) + "░" * (20 - int(v / max_v * 20))

    print(f"\n{'='*60}")
    print(f"  広報力スコアカード: {s.company_name}")
    print(f"{'='*60}")
    print(f"  総合スコア: {s.total_score:5.1f} / 100   グレード: [{s.grade}]")
    print(f"  {'─'*50}")
    print(f"  【量スコア (30点満点)】")
    print(f"    配信量          {s.volume_score:4.1f}/20  {bar(s.volume_score, 20)}")
    print(f"    継続活動        {s.recent_activity_score:4.1f}/10  {bar(s.recent_activity_score, 10)}")
    print(f"  【質スコア (40点満点)】")
    print(f"    カテゴリミックス {s.category_mix_score:4.1f}/15  {bar(s.category_mix_score, 15)}")
    print(f"    継続安定性      {s.consistency_score:4.1f}/10  {bar(s.consistency_score, 10)}")
    print(f"    成長トレンド    {s.growth_trajectory_score:4.1f}/15  {bar(s.growth_trajectory_score, 15)}")
    print(f"  【影響力スコア (30点満点)】")
    print(f"    インパクト      {s.impact_score:4.1f}/30  {bar(s.impact_score, 30)}")
    print(f"  {'─'*50}")
    print(f"  総リリース数: {s.total_releases} 件  |  活動月数: {s.active_months} ヶ月")
    print(f"  対象期間: {s.date_from} ～ {s.date_to}")
    print(f"  カテゴリ内訳: {s.top_categories}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # 最新のCSVを読み込む
    csv_files = sorted(glob.glob("releases_36528_*.csv"))
    if not csv_files:
        print("[!] CSVファイルが見つかりません。先に scraper.py を実行してください。")
        exit(1)

    csv_path = csv_files[-1]
    print(f"読み込み: {csv_path}")

    df = pd.read_csv(csv_path)
    score = score_company(df)
    print_scorecard(score)

    # JSON出力
    score_json = asdict(score)
    with open(f"score_36528_{datetime.now().strftime('%Y%m%d')}.json", "w", encoding="utf-8") as f:
        json.dump(score_json, f, ensure_ascii=False, indent=2)
    print(f"JSON保存: score_36528_{datetime.now().strftime('%Y%m%d')}.json")
