"""
複数企業の一括データ取得 → スコアリング → 比較レポート
"""

import asyncio
import json
import glob
import pandas as pd
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from scraper import fetch_releases
from scorer import score_company, print_scorecard, PRScore


DATA_DIR = Path("data")


async def collect_all(companies: list[dict], skip_existing: bool = True):
    """全企業のプレスリリースをデータ取得（既存CSVがあればスキップ）"""
    DATA_DIR.mkdir(exist_ok=True)
    for co in companies:
        cid = co["company_id"]
        name = co["name"]
        existing = sorted(DATA_DIR.glob(f"releases_{cid}_*.csv"))
        if skip_existing and existing:
            print(f"  [SKIP] {name} ({cid}) - 既存CSV: {existing[-1].name}")
            continue
        print(f"\n▶ 取得開始: {name} (company_id={cid})")
        releases = await fetch_releases(cid, max_clicks=30)
        if releases:
            df = pd.DataFrame([asdict(r) for r in releases])
            df = df.drop_duplicates(subset=["url"]).reset_index(drop=True)
            out = DATA_DIR / f"releases_{cid}_{datetime.now().strftime('%Y%m%d')}.csv"
            df.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"  → {len(df)} 件保存: {out}")
        else:
            print(f"  → データなし")
        await asyncio.sleep(3)  # サーバー負荷配慮


def score_all(companies: list[dict]) -> list[PRScore]:
    """保存済みCSVを読み込んでスコアリング"""
    scores = []
    for co in companies:
        cid = co["company_id"]
        name = co["name"]
        # dataディレクトリ内の最新CSV、なければカレントディレクトリも確認
        csvs = sorted(DATA_DIR.glob(f"releases_{cid}_*.csv")) \
             + sorted(Path(".").glob(f"releases_{cid}_*.csv"))
        if not csvs:
            print(f"  [SKIP] {name}: CSVなし")
            continue
        df = pd.read_csv(csvs[-1])
        score = score_company(df)
        score.company_name = name  # 表示名を上書き
        scores.append(score)
    return scores


def print_ranking(scores: list[PRScore]):
    """広報力ランキングを表示"""
    scores_sorted = sorted(scores, key=lambda s: s.total_score, reverse=True)

    print(f"\n{'='*70}")
    print(f"  広報力ランキング  ({datetime.now().strftime('%Y-%m-%d')} 時点)")
    print(f"{'='*70}")
    print(f"  {'順位':<4} {'企業名':<20} {'総合':>6} {'Grade':<5} "
          f"{'量':>5} {'質':>12} {'影響':>6} {'件数':>6}")
    print(f"  {'─'*66}")

    for i, s in enumerate(scores_sorted, 1):
        q_score = s.volume_score + s.recent_activity_score
        quality_score = s.category_mix_score + s.consistency_score + s.growth_trajectory_score
        print(
            f"  {i:<4} {s.company_name:<20} {s.total_score:>6.1f} "
            f"[{s.grade}]   {q_score:>4.1f}  {quality_score:>8.1f}  {s.impact_score:>6.1f}  {s.total_releases:>6}"
        )

    print(f"{'='*70}")
    print(f"  ※量(30点): 配信頻度+継続性  質(40点): カテゴリ+安定+トレンド  影響(30点): インパクト")


async def main():
    with open("companies.json", encoding="utf-8") as f:
        companies = json.load(f)

    print("=== 広報力測定ツール - 一括処理 ===\n")

    # Step1: データ収集
    print("【Step1】 プレスリリース収集")
    await collect_all(companies, skip_existing=True)

    # Step2: スコアリング
    print("\n【Step2】 スコアリング")
    scores = score_all(companies)

    # Step3: レポート
    print("\n【Step3】 ランキング表示")
    print_ranking(scores)

    # JSON出力
    results = [asdict(s) for s in scores]
    out_path = f"ranking_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n結果JSON: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
