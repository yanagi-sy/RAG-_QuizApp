# RAG Quiz App

RAG（Retrieval-Augmented Generation）を使ったQAとクイズアプリケーション。

## 概要

本アプリケーションは、RAG技術を活用してドキュメントから質問応答（QA）とクイズ生成を行うWebアプリケーションです。

- **QA機能**: ドキュメントに対して質問を投げかけ、ハイブリッド検索（Semantic＋キーワード→RRF融合→Cross-Encoderリランキング）で根拠を取得し、LLMで回答を生成する。
- **クイズ機能**: 指定した1資料から**教材サンプリング**で根拠を取得し、難易度別フィルタを経てLLMで○×問題を生成。○のみLLM生成、×はMutatorで補完。バリデーション・JSONパース（堅牢版＋修復リトライ）で品質を担保し、5問セットの生成・保存・プレイが可能。

技術詳細・データフロー・各ファイルの役割は **[技術スタックとデータフロー](./docs/09_技術スタックとデータフロー.md)** を参照してください。

## 技術要件

### Frontend
- Next.js 16.1.1 (App Router)
- React 19.2.3
- TypeScript ^5
- Tailwind CSS ^4

### Backend
- FastAPI 0.128.0
- Python 3.11+
- uvicorn 0.40.0
- PyMuPDF 1.26.7
- pydantic-settings 2.12.0
- httpx 0.27.2

### RAG・LLM
- ChromaDB 0.5.20（ベクトルDB）
- sentence-transformers（Embedding）
- Ollama（ローカルLLM、実装済み）
- Gemini API（将来対応予定）

## 前提条件

- Python 3.11以上
- Node.js 18以上
- npm または yarn

## 環境構築・起動

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # 必要に応じて編集

python -m uvicorn app.main:app --reload --port 8000 --log-level info
```

動作確認: `curl http://localhost:8000/health`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # 必要に応じて編集
npm run dev
```

## ドキュメント設定（manuals）

`manuals/` 配下の `.txt` / `.pdf` をQA・Quizの根拠として使用します。サーバー起動時に自動でインデックス構築されます。

- **手動再構築**: `python scripts/build_index.py`（`--force` で強制再構築）
- **ファイル追加・編集後**: サーバー停止 → `rm -rf backend/.chroma` → サーバー再起動

詳細は後述の「ドキュメント取り込み」を参照。

## ディレクトリ構成

```
rag-quiz-app/
├── backend/
│   ├── app/
│   │   ├── core/           # 設定・エラー
│   │   ├── docs/           # ドキュメント読込・チャンク分割
│   │   ├── rag/            # Embedding・ChromaDB・インデックス
│   │   ├── quiz/           # クイズ生成・サンプリング・バリデーション・保存
│   │   │   ├── duplicate_checker.py      # 重複チェック機能（statement・citation）
│   │   │   ├── fixed_question_converter.py  # 固定問題変換（4問目・5問目を×問題に）
│   │   ├── llm/            # Ollama・プロンプト
│   │   ├── routers/        # API（health, ask, quiz, judge, search, docs）
│   │   ├── schemas/        # リクエスト/レスポンス型
│   │   ├── search/         # キーワード検索・リランキング・スニペット
│   │   └── main.py
│   ├── scripts/            # build_index, audit 等
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx        # QA（/）
│   │   └── quiz/
│   │       ├── page.tsx    # クイズ（/quiz）生成・管理タブ
│   │       └── play/[id]/  # プレイ（/quiz/play/[id]）
│   ├── features/qa/        # QAPage, useAsk, AskForm, AnswerView, RetrievalSlider
│   ├── features/quiz/      # useQuiz, DifficultyPicker, QuizCard, JudgeButtons
│   └── lib/                # api, types
├── docs/                   # 要件定義・設計・09_技術スタックとデータフロー等
└── manuals/                # RAG対象（txt/pdf）
```

## 確認URL

| 種別 | URL |
|------|-----|
| Backend ヘルス | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| QA | http://localhost:3000/ |
| クイズ（生成・管理） | http://localhost:3000/quiz |
| クイズプレイ | http://localhost:3000/quiz/play/[quiz_set_id] |

## APIエンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | /health | 死活確認 |
| POST | /ask | 質問→ハイブリッド検索→LLM回答。`retrieval.semantic_weight`（0–1）で検索比率調整。`debug=true`で詳細出力。 |
| POST | /search | チャンク検索（キーワード＋2-gramフォールバック） |
| POST | /quiz/generate | クイズセット生成（5問、難易度・source_ids指定、保存オプション） |
| GET | /quiz/sets | クイズセット一覧 |
| GET | /quiz/sets/{id} | クイズセット詳細 |
| DELETE | /quiz/sets/{id} | クイズセット削除 |
| POST | /judge | 回答判定（正誤・解説・根拠） |
| GET | /docs/summary | ドキュメントサマリー |
| GET | /docs/sources | 利用可能ソース一覧 |

## 技術ドキュメント

- **[技術スタックとデータフロー](./docs/09_技術スタックとデータフロー.md)** — 技術解説・QA/Quizデータフロー・各ファイル概要
- [Quiz安定化実装](./docs/08_Quiz安定化実装.md) — 3層ガード（プロンプト・パース・修復）等

## 検索・QA・Quiz概要

### 検索
- **キーワード**: ストップワード除去・最小スコア閾値。0件時は2-gramフォールバック。
- **Semantic**: ChromaDB＋sentence-transformers（E5）。`backend/.chroma` に永続化。
- **ハイブリッド（/ask）**: Semantic＋キーワード → RRF融合 → Cross-Encoderリランキング → top_k 件を引用としてLLMに渡す。

### QA
- `POST /ask`: 引用を基にLLMで回答。LLM失敗時も `citations` を返すフォールバックあり。

### Quiz
- **教材サンプリング**: 検索ではなく、指定1資料からチャンクをランダムサンプル。難易度別キーワードで出題向きを選び、最低3件の引用を確保。
- **生成**: LLMで○のみ生成。×はMutatorで補完。パース・バリデーションで不合格は除外し、規定数に達するまで再試行。
- **セット**: 5問固定で生成・保存。`/quiz` で生成・管理、`/quiz/play/[id]` でプレイ。

## LLM（Ollama）設定

`.env` で主に以下を設定可能（省略時は `app/core/settings.py` のデフォルトを使用）:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT_SEC=120

# Quiz用
QUIZ_OLLAMA_NUM_PREDICT=800    # 生成トークン上限（長い問題文対応）
QUIZ_OLLAMA_TEMPERATURE=0.2
QUIZ_CONTEXT_TOP_N=4
QUIZ_QUOTE_MAX_LEN=200
QUIZ_TOTAL_QUOTE_MAX_CHARS=800

# 検索・リランク（/ask）
RERANK_ENABLED=true
RERANK_SCORE_THRESHOLD=-4.0
RERANK_SCORE_GAP_THRESHOLD=6.0
RRF_K=20
```

## ドキュメント取り込み

- `manuals/` に `.txt` / `.pdf` を配置すると起動時にインデックス化される。
- 追加・編集後は `backend/.chroma` を削除して再起動し、再構築する。
- PDFはPyMuPDFでテキスト抽出。スキャン画像のみのPDFは対象外。

## トラブルシューティング

### ChromaDB KeyError `_type`
- サーバー停止 → `rm -rf backend/.chroma` → 再起動で再構築。

### Quiz生成が遅い・タイムアウト
- Ollamaの応答速度、`QUIZ_OLLAMA_NUM_PREDICT`・`OLLAMA_TIMEOUT_SEC` を確認。
- 負荷軽減のため、Quizではリランクは原則OFF（`QUIZ_RERANK_ENABLED=false`）。

### /ask で引用が0件
- `manuals/` にドキュメントがあるか、起動ログでインデックス構築が成功しているか確認。
- `debug=true` で `zero_reason` 等を確認。

## 開発メモ

- Backend: `uvicorn --reload` でホットリロード。
- Frontend: Next.js 標準の開発サーバーでホットリロード。
- CORS: `.env` の `CORS_ORIGINS` で管理。
