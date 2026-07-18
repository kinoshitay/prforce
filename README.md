# prforce

PR TIMESのプレスリリースデータをもとに、企業の広報活動を収集・スコアリング・比較するダッシュボードです。

現在は、Pythonによるデータ収集とスコアリング、Streamlit版ダッシュボード、Cloudflare Pages向けの静的HTML生成を含みます。

## 主な機能

- 対象企業のPR TIMESプレスリリースを収集する
- 配信量、継続活動、カテゴリ構成、継続安定性、成長トレンド、影響力をスコア化する
- 企業別スコアとランキングをJSONで出力する
- ランキング、企業詳細、比較分析をダッシュボードで表示する
- `static/` と集計データから `dist/` に静的サイトを生成する

## データ処理の流れ

```text
companies.json
  ↓
scraper.py / batch_score.py
  ↓
data/releases_<company_id>_<date>.csv
  ↓
scorer.py
  ↓
ranking_<date>.json / dist/data.json
  ↓
Streamlit または静的HTML
```

## 主要ファイル

- `companies.json`: 対象企業、PR TIMESのcompany ID、カテゴリ
- `scraper.py`: Playwrightを使ったプレスリリース収集
- `batch_score.py`: 複数企業の収集、スコアリング、ランキング出力
- `scorer.py`: 0〜100点の広報力スコアを算出するエンジン
- `app.py`: Streamlit版のランキング画面
- `pages/`: Streamlit版の企業詳細・比較分析画面
- `build.py`: 静的サイト用データ生成とHTMLコピー
- `static/`: 静的サイトのHTMLソース
- `dist/`: Cloudflare Pagesへ配置する生成物
- `data/`: 収集済みCSV

## セットアップ

静的サイトのビルドに必要なPython依存関係をインストールします。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

スクレイピングやStreamlit版を使う場合は、実行環境に応じて `playwright`、`streamlit`、`plotly` も必要です。

```bash
pip install playwright streamlit plotly
python -m playwright install chromium
```

## データ収集とスコアリング

`companies.json` に登録された企業を対象に一括処理します。

```bash
python batch_score.py
```

既存の `data/releases_<company_id>_*.csv` がある企業は収集をスキップし、最新CSVを使ってスコアリングします。

単一企業向けの収集PoCは次で実行できます。対象company IDは現在 `scraper.py` 内で指定されています。

```bash
python scraper.py
```

## 静的サイトの生成

```bash
python build.py
```

`build.py` は最新CSVを読み込み、スコアとグラフ用データを `dist/data.json` に出力し、`static/` のHTMLを `dist/` へコピーします。Cloudflare Pagesでは、このコマンドをビルドコマンドとして使用できます。

## Streamlit版の起動

```bash
streamlit run app.py
```

## データ更新時の注意

- PR TIMESへのアクセス間隔と負荷に配慮してください。
- 収集前に `companies.json` のcompany IDを確認してください。
- 生成済みCSV、JSON、`dist/` を更新する場合は、差分に意図しない企業データが含まれていないか確認してください。
- スコアは公開データと現在のルールに基づく参考値であり、企業の広報活動全体を保証するものではありません。
