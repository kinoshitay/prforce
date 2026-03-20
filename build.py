"""
静的サイトビルドスクリプト
CSVデータ + scorer.py → dist/data.json を生成
Cloudflare Pages のビルドコマンド: python build.py
"""

import json
import os
import shutil
from pathlib import Path
from dataclasses import asdict

import pandas as pd
from scorer import score_company

DATA_DIR = Path("data")
DIST_DIR = Path("dist")


def format_date(d: str) -> str:
    if len(d) == 8:
        return f"{d[:4]}/{d[4:6]}/{d[6:]}"
    return d


def build():
    DIST_DIR.mkdir(exist_ok=True)

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

        # top_categories を list of {name, count} に変換（JSON-friendly）
        d["top_categories_list"] = [
            {"name": k, "count": v}
            for k, v in d["top_categories"].items()
        ]

        # 月別リリース数を計算（過去36ヶ月）
        df2 = df.copy()
        df2["published_at"] = pd.to_datetime(df2["published_at"], errors="coerce")
        df2 = df2.dropna(subset=["published_at"])
        df2["year_month"] = df2["published_at"].dt.strftime("%Y-%m")
        monthly = df2.groupby("year_month").size().reset_index(name="count")
        monthly = monthly.sort_values("year_month").tail(36)
        d["monthly_releases"] = monthly.to_dict(orient="records")

        scores.append(d)

        fname = csvs[-1].stem
        date_part = fname.split("_")[-1]
        if date_part > latest_date:
            latest_date = date_part

    scores.sort(key=lambda x: x["total_score"], reverse=True)

    output = {
        "updated_at": format_date(latest_date),
        "companies": scores,
    }

    out_path = DIST_DIR / "data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ {out_path} を生成しました（{len(scores)} 社）")


if __name__ == "__main__":
    build()
