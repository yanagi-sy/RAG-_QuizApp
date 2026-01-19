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
- **HTTPクライアント**: httpx 0.27.2

### LLM
- **実装済み**: Ollama（ローカル実行）
- **将来対応**: Gemini API（移行予定）

## 前提条件

- Python 3.11以上
- Node.js 18以上
- npm または yarn

## 環境構築＆起動手順

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

# .envファイルに以下の設定を追加（推奨）:
# CHROMA_DIR=backend/.chroma
# ※ ChromaDBの永続化ディレクトリを指定します。デフォルトは backend/.chroma です。

# サーバーを起動
uvicorn app.main:app --reload --port 8000
```

起動後、以下で動作確認：
```bash
curl http://localhost:8000/health
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
├── .cursor/                # Cursorプロジェクトルール
│   └── rules/              # ルールファイル（命名規則・開発方針）
├── .gitignore              # Git除外設定
├── backend/                # FastAPIバックエンド
│   ├── app/
│   │   ├── core/           # 設定・エラーハンドリング
│   │   │   ├── errors.py   # エラー定義
│   │   │   └── settings.py # 設定管理
│   │   ├── docs/           # ドキュメント読み込み・チャンク分割
│   │   │   ├── loader.py   # txt/pdf読み込み
│   │   │   ├── chunker.py  # LEN戦略で分割
│   │   │   └── models.py   # Document/Chunk型
│   │   ├── rag/            # RAG機能（Embedding・ベクトルDB・検索）
│   │   │   ├── embedding.py # Embedding生成（sentence-transformers）
│   │   │   ├── vectorstore.py # ChromaDB統合
│   │   │   ├── indexer.py  # インデックス自動構築
│   │   │   └── chunking.py # RAG用チャンキング
│   │   ├── quiz/           # クイズ用in-memoryストア
│   │   │   └── store.py    # quiz_id管理
│   │   ├── routers/        # APIルーター
│   │   │   ├── health.py   # GET /health
│   │   │   ├── ask.py       # POST /ask（ハイブリッド検索）
│   │   │   ├── search.py    # POST /search
│   │   │   ├── quiz.py      # POST /quiz
│   │   │   ├── judge.py     # POST /judge
│   │   │   └── docs.py      # GET /docs/summary
│   │   ├── search/          # 検索機能（キーワード検索）
│   │   │   ├── index.py     # 検索インデックス（キーワード検索）
│   │   │   └── ngram.py     # 2-gram検索（日本語対応）
│   │   ├── llm/             # LLMアダプタ層
│   │   │   ├── base.py      # LLMClient Protocol、例外定義
│   │   │   ├── ollama.py    # Ollamaクライアント実装
│   │   │   └── prompt.py    # プロンプト生成
│   │   ├── schemas/         # リクエスト/レスポンススキーマ
│   │   │   ├── ask.py
│   │   │   ├── quiz.py
│   │   │   ├── judge.py
│   │   │   └── common.py   # 共通型（Citation等）
│   │   └── main.py          # FastAPIアプリケーション
│   ├── .chroma/            # ChromaDB永続化ディレクトリ（自動生成）
│   └── requirements.txt     # Python依存パッケージ
├── frontend/               # Next.jsフロントエンド
│   ├── app/                # App Routerページ
│   │   ├── layout.tsx      # 共通レイアウト（ヘッダー）
│   │   ├── page.tsx        # QAトップ（/）
│   │   └── quiz/
│   │       └── page.tsx     # クイズ画面（/quiz）
│   ├── features/           # 機能別コンポーネント
│   │   ├── qa/             # QA機能
│   │   │   ├── QAPage.tsx
│   │   │   ├── useAsk.ts   # QA用カスタムフック
│   │   │   └── components/
│   │   │       ├── AskForm.tsx
│   │   │       ├── AnswerView.tsx
│   │   │       └── RetrievalSlider.tsx
│   │   └── quiz/           # クイズ機能
│   │       ├── QuizPage.tsx
│   │       ├── useQuiz.ts  # クイズ用カスタムフック
│   │       └── components/
│   │           ├── DifficultyPicker.tsx
│   │           ├── QuizCard.tsx
│   │           └── JudgeButtons.tsx
│   ├── lib/                # 共通ライブラリ
│   │   ├── api.ts          # APIクライアント
│   │   └── types.ts        # 型定義
│   └── package.json        # Node.js依存パッケージ
├── docs/                   # 設計書・ドキュメント
│   ├── 01_要件定義書.md
│   ├── 02_基本設計書.md
│   ├── 03_API設計書.md
│   ├── 04_詳細設計書.md
│   └── 05_進捗確認.md      # 設計書と現状実装の差分
└── manuals/                # RAG取り込み対象（txt/pdf）
    └── sample.txt          # サンプルドキュメント
```

## 確認URL

### Backend
- **ヘルスチェック**: http://localhost:8000/health
- **APIドキュメント**: http://localhost:8000/docs
- **APIサーバー**: http://localhost:8000

### Frontend
- **開発サーバー**: http://localhost:3000
- **QAページ**: http://localhost:3000/
- **クイズページ**: http://localhost:3000/quiz

## APIエンドポイント

### Health Check
- `GET /health` - サーバーの稼働状況確認

### QA
- `POST /ask` - 質問を送信し、回答を取得（ハイブリッド検索→LLM生成実装済み）
  - `retrieval.semantic_weight`（0.0-1.0、デフォルト0.7）で検索比率を調整可能
- `POST /search` - チャンクを検索（キーワード検索＋2-gramフォールバック）

### Quiz
- `POST /quiz` - クイズを生成
- `POST /judge` - クイズの回答を判定

### Docs
- `GET /docs/summary` - ドキュメントのサマリー（件数・文字数・チャンク数）

## ドキュメント取り込み

`manuals/` ディレクトリ（プロジェクトルート）に `.txt` または `.pdf` ファイルを配置すると、自動的に読み込まれます。

- **サマリー確認**: `GET /docs/summary`
- **PDF処理**: PyMuPDFを使用してテキスト抽出（スキャン画像は対象外）
- **チャンク分割**: 文字数に応じて自動的にチャンクサイズを調整（LEN戦略）
- **エラーログ**: 読み込めないPDFはログに記録（スキャンPDF等の検出）
- **自動インデックス構築**: サーバー起動時に`manuals/`配下のドキュメントを自動的にChromaDBにインデックス化
- **観測性強化**: 起動時にDOCS_DIR実パス、読み込みファイル一覧（txt/pdf別）、PDF抽出テキスト長、Chroma投入チャンクのsource分布をログ出力

### manuals/ のファイル追加・編集時の反映手順

**重要**: `manuals/` にファイルを追加または編集した場合、ChromaDBの再構築が必要です。

1. **サーバーを停止**（Ctrl+C）

2. **ChromaDBを削除して再構築**:
   ```bash
   # ChromaDBディレクトリを削除（CHROMA_DIR=backend/.chroma 前提）
   rm -rf backend/.chroma
   
   # サーバーを起動（起動時に自動的にインデックスが再構築される）
   cd backend
   source .venv/bin/activate  # 仮想環境が有効な場合
   uvicorn app.main:app --reload --port 8000
   ```

3. **反映確認の最短手順**:
   ```bash
   # 1. ヘルスチェック
   curl http://localhost:8000/health
   
   # 2. 追加ファイルにしかない単語で質問して、citations[].source に追加ファイル名が出ることを確認
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"追加ファイルにしかない単語"}'
   # レスポンスの citations[].source に追加したファイル名が含まれることを確認
   ```

**注意**: `backend/.chroma` ディレクトリはgit管理対象外です（`.gitignore`で除外）。ローカルのChromaDBデータは各環境で独立して管理されます。

### PDFが参照されない場合の確認手順

PDFファイルが回答に参照されない場合、以下の手順で原因を特定できます：

1. **起動ログで読み込み状況を確認**:
   - `PDF読み込み: <ファイル名> - Xページ, テキスト合計: Y文字` が表示されることを確認
   - テキスト合計が0文字の場合、画像PDF（スキャンPDF）の可能性があります
   - `Chroma投入チャンクのsource分布` にPDFファイル名が含まれ、チャンク数が0でないことを確認

2. **ChromaDB内のsource分布を確認**:
   ```bash
   # Pythonで確認スクリプト
   python3 -c "
   from app.rag.vectorstore import get_vectorstore, inspect_collection_sources
   from app.core.settings import settings
   collection = get_vectorstore(settings.chroma_dir)
   source_counts = inspect_collection_sources(collection)
   print('ChromaDB内のsource分布:')
   for source, count in sorted(source_counts.items()):
       print(f'  {source}: {count}チャンク')
   "
   ```

3. **PDF固有語で検索**:
   ```bash
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"PDFにしかない単語", "debug": true}' | jq '.citations[].source'
   ```

### RAGインデックス動作確認

1. **インデックス作成の確認**:
   - サーバー起動時に `build_index()` が自動実行されます
   - ログに以下の情報が表示されます:
     - `DOCS_DIR実パス: ... (exists=True)` - ドキュメントディレクトリの実パス
     - `読み込み対象ファイル: X件 - [...]` - 読み込み対象のファイル一覧
     - `PDF読み込み: <ファイル名> - Xページ, テキスト合計: Y文字` - PDF読み込み結果
     - `ドキュメント読み込み完了: TXT=Xファイル(...), PDF=Yファイル(...)` - txt/pdf別の読み込み結果
     - `Chroma投入チャンクのsource分布: {...}` - 各ファイルごとのチャンク数
     - `RAGインデックス作成完了: doc_count=X, chunk_count=Y` - 最終結果
   - 既にインデックスがある場合は "インデックスは既に存在します" と表示されます
   - **PDFが参照されない場合**: ログで以下を確認
     - PDFファイル名が「読み込み成功PDFファイル」に含まれているか
     - PDFのテキスト合計が0文字でないか（画像PDFの可能性）
     - 「Chroma投入チャンクのsource分布」にPDFが含まれ、チャンク数が0でないか

2. **`/ask` エンドポイントでcitations確認**:
   ```bash
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"機種依存文字が禁止なのはなぜ？"}'
   ```
   - レスポンスに `citations` 配列が含まれることを確認
   - `citations[].quote` が最大400文字であることを確認（`len(citation.quote)` で確認可能）
   - コレクションが空の場合は、ログに警告 "Chroma collection is empty. Run build_index first." が出力されます

3. **CHANGED: ChromaDB再生成手順（documents保存形式変更時、manuals/ファイル追加・編集時）**:
   ```bash
   # 1. サーバーを停止（Ctrl+C）
   
   # 2. ChromaDBを削除
   rm -rf backend/.chroma
   
   # 3. サーバーを起動（起動時に自動的にインデックスが再構築される）
   cd backend
   source .venv/bin/activate  # 仮想環境が有効な場合
   uvicorn app.main:app --reload --port 8000
   
   # 4. ログ確認（以下が表示されることを確認）
   # "CHROMA_DIR実パス: ..."
   # "RAGインデックス作成を開始します..."
   # "RAGインデックス作成完了: doc_count=X, chunk_count=Y"
   
   # 5. /ask を叩いてcitationsが返ることを確認
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"機種依存文字が禁止なのはなぜ？"}'
   
   # 6. citations[].quote が最大400文字であることを確認
   # （レスポンスをパースして各citationのquoteの長さを確認）
   ```
   - **なぜ再生成が必要か**: ChromaDBに保存する`documents`形式が変更された場合（例：400文字制限削除→全文保存）、既存DBとの整合性を保つために再生成が必要です。embedding（チャンク全文）とdocuments（保存内容）の整合性を保つためです。

## 検索機能

現在実装済みの検索機能：

### キーワード検索
- **キーワード検索**: スペース区切り＋ストップワード除去＋最小スコア閾値によるノイズ除去
- **ストップワード除去**: 助詞・助動詞など検索に不要な語を除外（「の」「は」「を」など）
- **最小スコア閾値**: 低品質マッチを除外（デフォルト=2、`KEYWORD_MIN_SCORE`で調整可能）
- **2-gram検索**: 日本語クエリ対応のフォールバック検索（キーワード検索で0件の場合に自動適用）
- **検索エンドポイント**: `POST /search` で検索結果を直接取得可能

日本語クエリ（スペース無し）でも検索可能です。例：`{"query":"機種依存文字"}` で検索できます。

### 意味検索（Semantic Search）
- **Embedding生成**: sentence-transformersを使用（デフォルト: `intfloat/multilingual-e5-small`）
- **ベクトルDB**: ChromaDBを使用（永続化、`backend/.chroma`に保存）
- **ベクトル検索**: コサイン類似度による意味検索
- **インデックス自動構築**: サーバー起動時に`manuals/`配下のドキュメントを自動的にインデックス化
- **根拠品質**: ChromaDBにはチャンク全文を保存し、APIレスポンス時に`quote`を最大400文字で切る（embeddingとdocumentsの整合性を保つ）

### ハイブリッド検索（RRF + Cross-Encoder）
- **`POST /ask`**: RRF順位融合 + Cross-Encoderリランキングによる高精度検索
- **候補品質管理**: 総チャンク数から動的に候補数を決定
  - `candidate_k = clamp(collection_count * 0.005, 20, 60)`
  - `rerank_n = clamp(candidate_k * 0.3, 10, 15)`
- **RRF（順位融合）**: min-max正規化を廃止し、順位ベースの融合
  - `rrf_score = w_sem / (20 + rank_sem) + w_kw / (20 + rank_kw)`
  - RRF_K=20で上位を重視、スコアの絶対的な品質を保持
- **Cross-Encoderリランキング**: 上位rerank_n件を再スコアリング
  - モデル: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`（多言語対応）
  - スコア閾値: `RERANK_SCORE_THRESHOLD=-1.5`（これ以下は除外）
  - `RERANK_ENABLED=true/false`で有効/無効切り替え
- **重み調整**: `retrieval.semantic_weight`（0.0-1.0、デフォルト0.7）でRRFの重み付けを調整
- **重複排除**: 同一ID（source, page, chunk_index）とquote先頭60文字で重複排除
- **デバッグ機能**: `debug=true`を指定すると、レスポンスに詳細なdebug情報が含まれます
  - `collection_count`, `candidate_k`, `rerank_n`, `top_k`: 候補数決定の詳細
  - `semantic_hits_count`, `keyword_hits_count`, `merged_count`: 各段階のヒット数
  - `pre_rerank`: リランキング前の上位候補（source, rrf_score, rank_sem, rank_kw）
  - `post_rerank`: リランキング後のスコア（source, rerank_score）
  - `final_selected_sources`: 最終的に選ばれたドキュメント

### QA統合
- `POST /ask`でハイブリッド検索結果を基にLLMで回答生成
- Ollama停止時でも`citations`を返す（フォールバック）

## LLM統合

### Ollama設定

`.env` ファイルで以下を設定可能（デフォルト値あり）:

```env
TOP_K=5                        # 最終的に返す件数
KEYWORD_MIN_SCORE=2            # キーワード検索の最小スコア閾値（ノイズ除去）

# 候補品質管理
CANDIDATE_RATIO=0.005          # 候補数の割合
CANDIDATE_MIN_K=20             # 候補数の最小値
CANDIDATE_MAX_K=60             # 候補数の最大値

# Cross-Encoderリランキング
RERANK_ENABLED=true            # リランキング有効/無効
RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1  # 多言語対応
RERANK_RATIO=0.3               # リランク対象数の割合
RERANK_MIN_N=8                 # リランク対象数の最小値
RERANK_MAX_N=12                # リランク対象数の最大値
RERANK_SCORE_THRESHOLD=-1.5    # スコア閾値（これ以下は除外）
RERANK_BATCH_SIZE=8            # バッチサイズ
RRF_K=20                       # RRF順位融合のKパラメータ（小さいほど上位重視）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT_SEC=30
```

### LLMアダプタ層

- **LLMClient Protocol**: 複数のLLM実装に対応可能なインターフェース
- **Ollama実装**: `httpx.AsyncClient` で `/api/chat` を呼び出し
- **プロンプト生成**: 質問と引用からシステム/ユーザーメッセージを構築
- **エラーハンドリング**: LLM失敗時もHTTP 200で `citations` を返す（フォールバック）

### 動作確認

```bash
# Ollamaが起動していることを確認
curl http://localhost:11434/api/tags

# /ask で質問（LLM回答が返る、デフォルトでhybrid retrieval）
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"機種依存文字が禁止なのはなぜ？"}'

# /ask で質問（semantic_weightを指定、Ollama停止でもcitations返る）
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"機種依存文字が禁止なのはなぜ？", "retrieval": {"semantic_weight": 0.8}}'

# /ask で質問（keyword検索のみ、semantic_weight=0.0）
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"機種依存文字が禁止なのはなぜ？", "retrieval": {"semantic_weight": 0.0}}'

# /ask で質問（debug=trueでデバッグ情報を取得）
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"機種依存文字が禁止なのはなぜ？", "retrieval": {"semantic_weight": 0.7}, "debug": true}' | jq '.debug'
```

**Hybrid Retrieval動作確認（Ollama停止時）**:
- Ollamaを停止した状態で `/ask` を呼び出すと、LLM回答は失敗しますが `citations` は返ります
- ログに `hybrid retrieval: semantic_hits=X, keyword_hits=Y, merged_hits=Z, top3_scores=[...], final_citations=N` が出力されます

**Hybrid Retrieval重み検証（debug機能使用）**:
- `semantic_weight=1.0`と`0.0`で比較すると、`debug.semantic_hits`と`debug.keyword_hits`が変化することを確認できます
- `debug.top3_scores`も重みに応じて変化します

## 開発メモ

- Backendは `--reload` オプションでホットリロード対応
- Frontendは Next.js の標準開発サーバーでホットリロード対応
- CORS設定は `.env` の `CORS_ORIGINS` で管理

### ChromaDB・Embedding管理

- **ChromaDBバージョン**: `requirements.txt`に`chromadb==0.5.20`を指定
- **Embeddingモデル**: `settings.py`で管理（デフォルト: `intfloat/multilingual-e5-small`）
  - `.env`で`EMBEDDING_MODEL`を指定して変更可能
- **ChromaDB永続化**: `backend/.chroma`に保存（デフォルト、`.env`の`CHROMA_DIR`で変更可能）
- **バージョン確認**: `pip list | grep chromadb`で実インストールバージョンを確認
- **バージョン不一致時の対処**: 
  - `pip install chromadb==0.5.20`で統一
  - または`requirements.txt`を実インストールバージョンに合わせて更新
- **DB互換エラー（KeyError '_type'）が発生した場合**:
  - サーバーを停止
  - `backend/.chroma`ディレクトリを削除（`rm -rf backend/.chroma`）
  - サーバーを再起動（起動時に自動的にインデックスが再構築されます）
- **CHANGED: ChromaDBを再生成する場合（根拠品質改善・documents保存形式変更など）**:
  - 理由: ChromaDBに保存するdocuments形式が変更された場合（例：400文字制限削除→全文保存）、既存DBとの整合性を保つために再生成が必要です
  - 手順:
    1. サーバーを停止（Ctrl+C）
    2. `backend/.chroma`ディレクトリを削除: `rm -rf backend/.chroma`
    3. サーバーを再起動（起動時に自動的にインデックスが再構築されます）
    4. ログに "RAGインデックス作成完了" が表示されることを確認
- **観測性**: 起動時にCHROMA_DIRの実パスをログ出力、検索時に件数・スコアをログ出力
