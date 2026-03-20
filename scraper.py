"""
PR Times スクレイパー (Playwright版 / 「もっと見る」ボタン対応)
対象: https://prtimes.jp/main/html/searchrlp/company_id/{company_id}
"""

import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import json
import re
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PressRelease:
    title: str
    url: str
    published_at: str          # ISO8601 or "YYYY-MM-DD HH:MM"
    company_name: str
    company_id: str


async def fetch_releases(company_id: str, max_clicks: int = 20) -> list[PressRelease]:
    """
    「もっと見る」ボタンを繰り返しクリックして全記事を取得する。
    max_clicks: 最大クリック回数（1クリックで約20件追加）
    """
    url = f"https://prtimes.jp/main/html/searchrlp/company_id/{company_id}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
        )

        print(f"  読み込み中: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 企業名
        company_name = await _get_company_name(page)

        # 初期件数
        initial = await page.query_selector_all("article")
        print(f"  初期表示: {len(initial)} 件")

        # 「もっと見る」を繰り返しクリック
        for i in range(max_clicks):
            more_btn = await page.query_selector("button._button_jsqz1_1")
            # テキストで絞り込み
            if more_btn:
                txt = (await more_btn.text_content() or "").strip()
                if txt != "もっと見る":
                    more_btn = None

            if not more_btn:
                # クラス名が変わる可能性を考慮してテキストで探す
                btns = await page.query_selector_all("button")
                for btn in btns:
                    if (await btn.text_content() or "").strip() == "もっと見る":
                        more_btn = btn
                        break

            if not more_btn:
                print(f"  「もっと見る」ボタンなし → 全件取得完了")
                break

            await more_btn.scroll_into_view_if_needed()
            await more_btn.click()
            await page.wait_for_timeout(2000)

            current = await page.query_selector_all("article")
            print(f"  クリック {i+1}: {len(current)} 件")

        # 全記事をパース
        articles = await page.query_selector_all("article")
        releases = []
        for article in articles:
            r = await _parse_article(article, company_id, company_name)
            if r:
                releases.append(r)

        await browser.close()

    return releases


async def _get_company_name(page) -> str:
    """企業名を取得"""
    try:
        # OGタイトルから取得
        meta = await page.query_selector("meta[property='og:title']")
        if meta:
            content = await meta.get_attribute("content") or ""
            # "LayerXのプレスリリース｜PR TIMES" → "LayerX"
            name = content.split("のプレスリリース")[0].strip()
            if name:
                return name
    except Exception:
        pass
    return ""


async def _parse_article(article, company_id: str, company_name: str) -> Optional[PressRelease]:
    """article要素 → PressRelease"""
    # タイトル
    title_el = await article.query_selector("h2[data-testid='release-title'], h2, h3")
    if not title_el:
        return None
    title = (await title_el.text_content() or "").strip()
    if not title:
        return None

    # URL (wrapperLinkがhrefを持つ)
    link_el = await article.query_selector("a[href*='/main/html/rd/p/'], a[href*='/main/html/detail/']")
    if not link_el:
        link_el = await article.query_selector("a[href]")
    href = (await link_el.get_attribute("href") or "") if link_el else ""
    url = f"https://prtimes.jp{href}" if href.startswith("/") else href

    # 日時
    time_el = await article.query_selector("time[datetime]")
    published_at = ""
    if time_el:
        published_at = (await time_el.get_attribute("datetime") or "").strip()
        if published_at:
            # ISO8601 → "YYYY-MM-DD HH:MM"
            published_at = published_at[:16].replace("T", " ")

    return PressRelease(
        title=title,
        url=url,
        published_at=published_at,
        company_name=company_name,
        company_id=company_id,
    )


def analyze(df: pd.DataFrame) -> dict:
    """基本集計"""
    if df.empty:
        return {}

    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df_dated = df.dropna(subset=["published_at"]).copy()
    result: dict = {"total": len(df), "dated_count": len(df_dated)}

    if not df_dated.empty:
        df_dated["year_month"] = df_dated["published_at"].dt.to_period("M")
        monthly = df_dated.groupby("year_month").size().rename("count")
        result.update({
            "date_range": {
                "from": str(df_dated["published_at"].min().date()),
                "to":   str(df_dated["published_at"].max().date()),
            },
            "monthly_avg": round(float(monthly.mean()), 2),
            "monthly_max": int(monthly.max()),
            "most_active_month": str(monthly.idxmax()),
            "monthly_breakdown": {str(k): int(v) for k, v in monthly.items()},
        })

    return result


async def main():
    COMPANY_ID = "36528"  # LayerX
    print(f"=== PR Times スクレイピング PoC ===")
    print(f"対象: company_id={COMPANY_ID} (LayerX)\n")

    releases = await fetch_releases(COMPANY_ID, max_clicks=20)

    if not releases:
        print("\n[!] データが取得できませんでした")
        return

    df = pd.DataFrame([asdict(r) for r in releases])
    df = df.drop_duplicates(subset=["url"]).reset_index(drop=True)

    result = analyze(df)
    print("\n=== 集計結果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    output_path = f"releases_{COMPANY_ID}_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nCSV保存: {output_path}")
    print(f"\n--- 先頭10件 ---")
    print(df[["published_at", "title"]].head(10).to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())
