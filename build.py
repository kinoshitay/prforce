"""
静的サイトビルドスクリプト
CSVデータ + scorer.py → dist/ に静的サイトを生成
Cloudflare Pages のビルドコマンド: python build.py
"""

import json
import shutil
from pathlib import Path
from dataclasses import asdict

import pandas as pd
from scorer import score_company, infer_category

DATA_DIR = Path("data")
DIST_DIR = Path("dist")
STATIC_DIR = Path("static")


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

        # top_categories を list of {name, count} に変換
        d["top_categories_list"] = [
            {"name": k, "count": v}
            for k, v in d["top_categories"].items()
        ]

        # --- 月別リリース数（全期間） ---
        df2 = df.copy()
        df2["published_at"] = pd.to_datetime(df2["published_at"], errors="coerce")
        df2 = df2.dropna(subset=["published_at"])
        df2["title_cat"] = df2["title"].apply(infer_category)
        df2["year_month"] = df2["published_at"].dt.strftime("%Y-%m")

        monthly = df2.groupby("year_month").size().reset_index(name="count")
        monthly = monthly.sort_values("year_month")
        d["monthly_releases"] = monthly.to_dict(orient="records")

        # --- カテゴリ分布 ---
        cat_counts = df2["title_cat"].value_counts().reset_index()
        cat_counts.columns = ["category_name", "count"]
        d["category_distribution"] = cat_counts.to_dict(orient="records")

        # --- 直近12ヶ月カテゴリ別月次 ---
        now = pd.Timestamp.now()
        df_recent = df2[df2["published_at"] >= now - pd.DateOffset(months=12)].copy()
        cat_monthly = (
            df_recent.groupby(["year_month", "title_cat"]).size()
            .reset_index(name="count")
            .sort_values("year_month")
        )
        cat_monthly.columns = ["year_month", "category_name", "count"]
        d["category_monthly"] = cat_monthly.to_dict(orient="records")

        # --- 直近10件リリース ---
        df2_sorted = df2.sort_values("published_at", ascending=False)
        recent = []
        for _, row in df2_sorted.head(10).iterrows():
            recent.append({
                "date": row["published_at"].strftime("%Y-%m-%d"),
                "title": row["title"],
                "category": row["title_cat"],
                "url": row.get("url", ""),
            })
        d["recent_releases"] = recent

        scores.append(d)

        fname = csvs[-1].stem
        date_part = fname.split("_")[-1]
        if date_part > latest_date:
            latest_date = date_part

    scores.sort(key=lambda x: x["total_score"], reverse=True)

    output = {
        "updated_at": format_date(latest_date),
        "total_companies": len(scores),
        "total_releases": sum(s["total_releases"] for s in scores),
        "avg_score": round(sum(s["total_score"] for s in scores) / max(len(scores), 1), 1),
        "companies": scores,
    }

    # data.json 出力
    out_path = DIST_DIR / "data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[OK] {out_path} ({len(scores)} companies)")

    # static/ → dist/ にHTMLファイルをコピー
    if STATIC_DIR.exists():
        for f in STATIC_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, DIST_DIR / f.name)
                print(f"[OK] copied {f.name}")

    print(f"=== Build complete: {len(scores)} companies, dist/ ready ===")


if __name__ == "__main__":
    build()
