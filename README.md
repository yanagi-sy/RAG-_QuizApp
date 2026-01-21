# RAG Quiz App

RAG（Retrieval-Augmented Generation）を使ったQAとクイズアプリケーション。

## 概要

本アプリケーションは、RAG技術を活用してドキュメントから質問応答（QA）とクイズ生成を行うWebアプリケーションです。

- **QA機能**: ドキュメントに対して質問を投げかけ、関連する情報を基に回答を生成（ハイブリッド検索 + LLM）
- **クイズ機能**: ドキュメントから○×形式のクイズを自動生成し、回答を判定（**教材サンプリング方式** + 難易度別フィルタ + LLM + バリデーション）
  - **2026-01-20更新 (1)**: 検索ベースから教材サンプリング方式に変更し、全資料 / 全難易度で必ず3件以上の引用を確保
  - **2026-01-20更新 (2)**: LLMには「○（正しい断言文）」のみ生成させ、×はコードで自動生成することで品質向上
  - **2026-01-20更新 (3)**: MVP版として生成数を3問に固定、タイムアウト対策として入力/出力を厳格に制限
  - **2026-01-20更新 (4)**: LLM負担計測機能を追加（prompt_chars, output_chars等）、Ollama応答抽出を堅牢化
  - **2026-01-21更新 (5)**: Quiz不安定問題のデバッグ観測ログを追加（PIPE/PARSE/QUIZ_OBSERVE）、原因調査レポート作成
  - **2026-01-21更新 (6)**: ImportError修正（quiz.py, judge.pyの不正なimportを削除）、サーバー起動問題を解決
  - **2026-01-21更新 (7)**: Parser改修（count件にtruncate + citations堅牢化）、LLM不安定出力を機械的に安定化

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

## テスト実行

### チャンク監査（強盗/万引き混在チェック）

```bash
cd backend
source .venv/bin/activate
python scripts/audit_chunks.py --keyword 強盗 --context-n 1

# 結果確認
cat ../docs/REPORT_chunk_audit.md
```

### /ask 回帰テスト（引用品質チェック）

```bash
cd backend
source .venv/bin/activate
python test_ask_citations.py
```

期待結果:
- ✅ PASS: 強盗の質問
- ✅ PASS: 防災の質問

---

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
│   │   │   ├── chunking.py # RAG用チャンキング
│   │   │   ├── hybrid_retrieval.py # ハイブリッド検索（RRF + Cross-Encoder）
│   │   │   └── quiz_retrieval.py # Quiz専用RAG検索（閾値なし）
│   │   ├── quiz/           # クイズ生成・バリデーション
│   │   │   ├── store.py    # quiz_id管理（in-memory）
│   │   │   ├── generator.py # LLM生成＋バリデーション統合
│   │   │   ├── parser.py   # JSONパース
│   │   │   └── validator.py # バリデーション（○×専用）
│   │   ├── routers/        # APIルーター
│   │   │   ├── health.py   # GET /health
│   │   │   ├── ask.py       # POST /ask（ハイブリッド検索）
│   │   │   ├── search.py    # POST /search
│   │   │   ├── quiz.py      # POST /quiz/generate（クイズ生成）
│   │   │   ├── judge.py     # POST /judge（クイズ判定）
│   │   │   ├── docs.py      # GET /docs/summary
│   │   │   └── sources.py   # GET /sources（資料一覧取得）
│   │   ├── search/          # 検索機能（キーワード検索・リランキング）
│   │   │   ├── index.py     # 検索インデックス（キーワード検索）
│   │   │   ├── ngram.py     # 2-gram検索（日本語対応）
│   │   │   ├── keyword.py   # キーワード検索（ストップワード除去）
│   │   │   ├── reranker.py  # Cross-Encoderリランキング
│   │   │   ├── snippet.py   # スニペット生成
│   │   │   ├── stopwords.py # ストップワード定義
│   │   │   └── cache.py     # キャッシュ機能
│   │   ├── llm/             # LLMアダプタ層
│   │   │   ├── base.py      # LLMClient Protocol、例外定義
│   │   │   ├── ollama.py    # Ollamaクライアント実装
│   │   │   └── prompt.py    # プロンプト生成（QA + Quiz）
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
│   │       ├── QuizPage.tsx # フェーズ管理
│   │       ├── useQuiz.ts  # クイズ用カスタムフック
│   │       └── components/
│   │           ├── SetupPhase.tsx # セットアップフェーズ
│   │           ├── PlayingPhase.tsx # プレイフェーズ
│   │           ├── ResultPhase.tsx # 結果フェーズ
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
│   ├── 05_進捗確認.md      # 設計書と現状実装の差分
│   ├── 06_リファクタリング記録.md # リファクタリング履歴
│   ├── 09_技術スタックとデータフロー.md # 技術スタック・アーキテクチャ
│   ├── REPORT_root_cause_quiz.md # Quiz不安定問題の原因調査レポート
│   └── DEBUG_IMPLEMENTATION_SUMMARY.md # デバッグ観測ログ実装サマリ
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
- `POST /quiz/generate` - クイズを生成（難易度別、LLM統合、JSONパース＋バリデーション）
- `POST /judge` - クイズの回答を判定（正誤判定のみ、解説生成は未実装）

### Docs
- `GET /docs/summary` - ドキュメントのサマリー（件数・文字数・チャンク数）
- `GET /sources` - 資料一覧を取得（source_idsのリスト）

## 技術ドキュメント

システムの技術詳細については、以下のドキュメントを参照してください：

- **[技術スタックとデータフロー](./docs/09_技術スタックとデータフロー.md)** - 使用技術の解説、QA/Quiz機能のデータフロー図、RAGパイプライン詳細
- [Quiz教材サンプリング実装](./docs/07_Quiz教材サンプリング実装.md) - Quiz機能の「教材サンプリング方式」の詳細
- [Quiz安定化実装](./docs/08_Quiz安定化実装.md) - 3層ガード（Prompt強化 + Robust parse + JSON修復）の詳細
- [リファクタリング記録](./docs/06_リファクタリング記録.md) - 過去のリファクタリング履歴

## Quiz生成品質向上（○/×分離戦略）

**2026-01-20実装**: Quiz生成の品質を向上させるため、以下の戦略を採用しました。

### 課題

- LLM出力が不安定で `quizzes=0` になることがある（JSON崩れ/空/余計な文章）
- ○×として成立しない問題が多い（判定不能、疑問形、一般論、曖昧表現）
- 「問題になっていない」など、真偽が教材から決められない文が混ざる

### 解決策：○/×分離戦略

1. **LLMには「○（正しい断言文）」のみ生成させる**
   - 教材（citations）に基づく事実を、そのまま断言する
   - 曖昧表現（「場合がある」「望ましい」等）を禁止
   - 疑問形（「?」「でしょうか」）を禁止

2. **×はコードで自動生成（Mutator）**
   - ○の statement を1点だけズラして×を生成
   - 数値の反転（+1/-1）、禁止/許可の反転、必須/任意の反転など
   - Validator で品質チェックし、合格したもののみ採用

3. **Validatorの強化**
   - 疑問形チェック（`?`, `？`, `でしょうか`, `ですか`）
   - 短文チェック（12文字未満は reject）
   - 曖昧表現チェック（21種類の表現をリスト化）
   - 不合格理由を返却（`reason`）し、debug で集計

4. **Debug観測性の向上**
   - `debug.generated_true_count`: 採用された○の件数
   - `debug.generated_false_count`: 採用された×の件数
   - `debug.dropped_reasons`: 不合格理由の集計（reason → count）

### 実装構成

- `backend/app/quiz/validator.py`: 強化版バリデーター（曖昧表現チェック等）
- `backend/app/quiz/mutator.py`: ○→×変換（1点だけズラす）
- `backend/app/quiz/generator.py`: 生成ロジック（○のみ生成 → ×はmutatorで生成）
- `backend/app/llm/prompt.py`: LLMプロンプト（○のみ生成を指示）

### テスト

```bash
cd backend
./test_quiz_quality.sh
```

- 全source × beginner/intermediate/advanced で `quizzes.length == 5` を確認
- `dropped_reasons` をログ出力し、改善の観測ができること

### MVP版（2026-01-20追加）: 生成数3問固定 + タイムアウト対策

タイムアウト問題を回避するため、以下の制限を導入しました：

1. **生成数を3問に固定**
   - `QuizGenerateRequest.count` のデフォルトを 3 に変更
   - `min(req.count, 3)` で最大3問に制限（MVP上限）

2. **LLM入力の厳格な制限**
   - Citations: 最大4件（`quiz_context_top_n=4`）
   - Quote: 最大200文字/件（`quiz_quote_max_len=200`）
   - 総Quote文字数: 最大800文字（`quiz_total_quote_max_chars=800`）

3. **LLM出力の制限**
   - `num_predict=400`（生成トークン数上限）
   - `temperature=0.2`（低温度で安定出力）
   - `explanation`: 1文、最大80文字に誘導

4. **プロンプト簡潔化**
   - levelごとにテンプレートを2種類に絞る
   - 冗長な説明文を削除、JSON出力のみに集中

5. **LLM負担計測機能**
   - `llm_prompt_chars`: プロンプト全体の文字数
   - `llm_input_citations_count`: 実際に渡した引用数
   - `llm_input_total_quote_chars`: 実際に渡した引用の総文字数
   - `llm_output_chars`: LLM生出力の文字数
   - `llm_output_preview_head`: LLM生出力の先頭200文字
   - `llm_num_predict`, `llm_temperature`, `llm_timeout_sec`: LLMパラメータ

6. **Ollama応答抽出の堅牢化**
   - `extract_ollama_text()`: 複数のレスポンス形式に対応
   - chat API形式、generate API形式、streaming形式など
   - デバッグログで `ollama_raw_type` と `ollama_raw_keys` を出力

### 受け入れ条件

- すべての source（登録マニュアル）について
  - beginner / intermediate / advanced
  - count=3（MVP固定）
  - quizzes の長さが 3 で安定する（タイムアウト回避）
- quizzes は true_false のみ
- statement は疑問形ではない宣言文
- 曖昧表現・判定不能文が混ざらない（validatorで落ちる）
- /ask の挙動・コード・設定に変更がない

### Quiz不安定問題のデバッグ（2026-01-21追加）

Quiz生成の火元（遅延/失敗/品質崩れ）を特定するための観測ログを実装しました。

**観測ログ**:
- `[PIPE:BEFORE_MUTATOR]`: Mutator実行前のstatement確認
- `[PARSE:RAW_PREVIEW]`, `[PARSE:JSON_KEYS]`, `[PARSE:QUIZ_ITEM_TYPES]`: LLM出力とJSON型確認
- `[QUIZ_OBSERVE:REQUEST]`, `[QUIZ_OBSERVE:RESPONSE]`: Ollama推論の観測

**検証手順**:
```bash
cd backend
./test_quiz_debug.sh
```

実行すると：
- 3パターン（count=1/3, save=true含む）を各3回実行
- 結果を `/tmp/quiz_debug_*/` に保存
- サマリを自動生成

**ドキュメント**:
- `docs/REPORT_root_cause_quiz.md`: 原因調査レポート（火元の断定、修正方針）
- `docs/DEBUG_IMPLEMENTATION_SUMMARY.md`: 実装内容の詳細

**火元の仮説**:
1. 🔥 後処理適用順序問題（Mutator前に正規化が未実行）
2. 🔥 LLM出力型不整合（quizzes[i]がstrになる）
3. 🔥 Ollama推論遅延（20〜60秒/問）

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
  - **普遍的な品質管理**:
    - 絶対値閾値: `RERANK_SCORE_THRESHOLD=-1.5`（基本品質保証）
    - 相対的差分: `RERANK_SCORE_GAP_THRESHOLD=6.0`（トップとの差が6.0以上なら除外）
    - 資料セットが変わっても機能する相対的判定
  - `RERANK_ENABLED=true/false`で有効/無効切り替え
- **重み調整**: `retrieval.semantic_weight`（0.0-1.0、デフォルト0.7）でRRFの重み付けを調整
- **重複排除**: 同一ID（source, page, chunk_index）とquote先頭60文字で重複排除
- **デバッグ機能**: `debug=true`を指定すると、レスポンスに詳細なdebug情報が含まれます
  - `collection_count`, `candidate_k`, `rerank_n`, `top_k`: 候補数決定の詳細
  - **段階別カウント**（0件化する地点の特定用）:
    - `semantic_before_filter`, `semantic_after_filter`: semantic検索のフィルタ前後の件数
    - `keyword_before_filter`, `keyword_after_filter`: keyword検索のフィルタ前後の件数
    - `merged_count`: RRFマージ後の件数
    - `post_rerank_count`: リランキング後の件数
    - `after_threshold_count`: 閾値フィルタ通過後の件数
    - `final_citations_count`: 最終的なcitationsの件数
    - `zero_reason`: 0件になった理由（例: "all_candidates_removed_by_rerank_threshold"）
  - `pre_rerank`: リランキング前の上位候補（source, rrf_score, rank_sem, rank_kw）
  - `post_rerank`: リランキング後のスコア（source, rerank_score）
  - `final_selected_sources`: 最終的に選ばれたドキュメント
  - **source_filter対応**:
    - `allowed_sources`: 検索対象のsource一覧（source_filter指定時）
    - `semantic_sources_before_unique`, `keyword_sources_before_unique`: フィルタ前の候補source一覧
    - Unicode正規化対応により、日本語ファイル名でも正しくフィルタリング可能

### QA統合
- `POST /ask`でハイブリッド検索結果を基にLLMで回答生成
- Ollama停止時でも`citations`を返す（フォールバック）
- **source_filter対応**: リクエストに`source_ids`を指定して特定の資料のみを検索対象にできます
  - Unicode正規化により、日本語ファイル名でも正しく動作
  - デバッグ情報で各段階のフィルタ結果を確認可能

### Quiz統合
- `POST /quiz/generate`でQuiz専用RAG検索を基にLLMでクイズを生成
- **Quiz専用RAG検索**（`quiz_retrieval.py`）:
  - semantic検索のみ（キーワード検索なし、抽象的なクエリに強い）
  - rerankは順位付けのみ（閾値で全落ちさせない）
  - 最低N件を必ず返す（LLM生成の材料確保）
  - `/ask` とは独立した処理フロー
- **LLM生成**（`generator.py`）:
  - 難易度別プロンプト生成
  - 再試行制御（LLMタイムアウト・パースエラー時に最大2回試行）
  - バリデーション統合
- **JSONパース**（`parser.py`）:
  - マークダウンブロック対応
  - question → statement互換性対応
  - UUID自動生成
- **バリデーション**（`validator.py`）:
  - ○×問題専用バリデーション
  - 疑問形禁止（`?` `？` を除外）
  - citations の存在・内容チェック

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
RERANK_SCORE_THRESHOLD=-1.5    # 絶対値閾値（基本品質保証）
RERANK_SCORE_GAP_THRESHOLD=6.0 # トップとの差分閾値（普遍的な品質管理）
RERANK_BATCH_SIZE=8            # バッチサイズ
RRF_K=20                       # RRF順位融合のKパラメータ（小さいほど上位重視）

# Quiz専用設定
QUIZ_CANDIDATE_K=30            # Quiz生成時の候補取得件数
QUIZ_SEMANTIC_WEIGHT=1.0       # Quiz検索のsemantic重み（1.0 = semantic検索のみ）
QUIZ_RERANK_ENABLED=true       # Quiz検索のrerank有効/無効
QUIZ_CONTEXT_TOP_N=5           # Quiz生成時のコンテキスト件数

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

# /quiz/generate で単独資料のクイズ生成テスト（debug=trueで段階別カウント確認）
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{"level":"beginner","count":3,"source_ids":["sample.txt"],"debug":true}' | jq '.debug'
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

## トラブルシューティング

### ImportError: cannot import name 'QuizItem' from 'app.quiz.store'

**問題**: サーバー起動時に`quiz.py`または`judge.py`が存在しないモジュールをimportしようとしてエラーになる

**原因**: 旧設計の`QuizItem`、`save_quiz`、`get_quiz`が削除されたが、importが残っている

**解決策（2026-01-21に修正済み）**:
- `backend/app/routers/quiz.py`: ダミー実装を簡略化、固定quiz_idを返す
- `backend/app/routers/judge.py`: ダミー実装を簡略化、常にtrueが正解

**確認方法**:
```bash
cd backend
source .venv/bin/activate
python -c "from app.main import app; print('✓ Import successful!')"
```

### Quiz生成が遅い・タイムアウトする

**問題**: `/quiz/generate`が20〜60秒かかる、またはタイムアウトする

**原因**:
1. Ollama推論が遅い（モデルサイズ、CPU/GPU、num_ctx/num_predict）
2. 後処理順序問題（Mutator前に正規化が未実行）
3. LLM出力型不整合（救済処理が頻発）

**デバッグ方法**:
```bash
cd backend
./test_quiz_debug.sh
cat /tmp/quiz_debug_*/REPORT_summary.txt
```

**観測ログ**:
- `[QUIZ_OBSERVE:REQUEST]`: prompt_chars, num_predict, num_ctx等
- `[QUIZ_OBSERVE:RESPONSE]`: total_duration_ns, eval_count等
- `[PIPE:BEFORE_MUTATOR]`: statement_preview（【source】等が残っているか確認）
- `[PARSE:QUIZ_ITEM_TYPES]`: types（strが含まれるか確認）

**詳細**: `docs/REPORT_root_cause_quiz.md`を参照

### /ask回帰テスト

Quiz関連の修正後、/askが正常に動作することを確認：

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"テスト質問"}' | jq '.answer, .citations | length'
```

期待結果:
- `answer`が返る（LLM失敗時はnullでもOK）
- `citations`が返る（最低1件以上）
