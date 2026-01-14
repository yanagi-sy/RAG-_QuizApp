# RAG Quiz App

RAG（Retrieval-Augmented Generation）を使ったQAとクイズアプリケーション。

## 概要

本アプリケーションは、RAG技術を活用してドキュメントから質問応答（QA）とクイズ生成を行うWebアプリケーションです。

- **QA機能**: ドキュメントに対して質問を投げかけ、関連する情報を基に回答を生成
- **クイズ機能**: ドキュメントから○×形式のクイズを生成し、回答を判定

## 技術要件

### Frontend
- **フレームワーク**: Next.js 16.1.1 (App Router)
- **言語**: TypeScript
- **UI**: React 19.2.3 + Tailwind CSS 4
- **ビルドツール**: Next.js標準

### Backend
- **フレームワーク**: FastAPI 0.128.0
- **言語**: Python 3.11+
- **ASGIサーバー**: uvicorn 0.40.0
- **PDF処理**: PyMuPDF 1.26.7
- **設定管理**: pydantic-settings 2.12.0

### LLM
- **MVP**: Ollama（ローカル実行）
- **将来**: Gemini API（移行予定）

## 前提条件

- Python 3.11以上
- Node.js 18以上
- npm または yarn

## 環境構築手順

### Backend

```bash
cd backend

# 仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt

# 環境変数を設定（.env.exampleをコピー）
cp .env.example .env

# サーバーを起動
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# 依存パッケージをインストール
npm install

# 環境変数を設定（.env.exampleをコピー）
cp .env.example .env

# 開発サーバーを起動
npm run dev
```

## ディレクトリ構成

```
rag-quiz-app/
├── backend/                 # FastAPIバックエンド
│   ├── app/
│   │   ├── core/           # 設定・エラーハンドリング
│   │   ├── docs/           # ドキュメント読み込み・チャンク分割
│   │   ├── quiz/           # クイズ用in-memoryストア
│   │   └── routers/        # APIルーター
│   ├── .venv/              # Python仮想環境
│   ├── requirements.txt    # Python依存パッケージ
│   └── .env.example        # 環境変数テンプレート
├── frontend/               # Next.jsフロントエンド
│   ├── app/                # App Routerページ
│   ├── features/           # 機能別コンポーネント
│   │   ├── qa/            # QA機能
│   │   └── quiz/          # クイズ機能
│   ├── lib/                # 共通ライブラリ
│   ├── package.json        # Node.js依存パッケージ
│   └── .env.example        # 環境変数テンプレート
└── docs/                   # 設計書・ドキュメント
    ├── 01_要件定義書.md
    ├── 02_基本設計書.md
    ├── 03_API設計書.md
    └── 04_詳細設計書.md
```

## 起動後の確認URL

### Backend
- **APIサーバー**: http://localhost:8000
- **ヘルスチェック**: http://localhost:8000/health
- **APIドキュメント**: http://localhost:8000/docs
- **ルートエンドポイント**: http://localhost:8000/

### Frontend
- **開発サーバー**: http://localhost:3000
- **QAページ**: http://localhost:3000/
- **クイズページ**: http://localhost:3000/quiz

## APIエンドポイント

### Health Check
- `GET /health` - サーバーの稼働状況確認

### QA
- `POST /ask` - 質問を送信し、回答を取得

### Quiz
- `POST /quiz` - クイズを生成
- `POST /judge` - クイズの回答を判定

### Docs
- `GET /docs/summary` - ドキュメントのサマリー（件数・文字数・チャンク数）

## ドキュメント取り込み

`docs/` ディレクトリ（プロジェクトルート）に `.txt` または `.pdf` ファイルを配置すると、自動的に読み込まれます。

- **サマリー確認**: `GET /docs/summary`
- **PDF処理**: PyMuPDFを使用してテキスト抽出（スキャン画像は対象外）
- **チャンク分割**: 文字数に応じて自動的にチャンクサイズを調整

## 開発メモ

- Backendは `--reload` オプションでホットリロード対応
- Frontendは Next.js の標準開発サーバーでホットリロード対応
- CORS設定は `.env` の `CORS_ORIGINS` で管理
