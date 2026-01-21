# 実装サマリー: チャンク混在 & Citations品質改善

## 実施日
2026-01-21

## 目的
1. `/ask`で「強盗」質問時に「万引き」チャンクが引用される根拠ズレを解消
2. `/quiz`でcitationsが空になる問題の再発防止（既にParser改修で対応済み）

---

## 実施内容

### 1. チャンク詳細監査スクリプトの追加

**新規ファイル**: `backend/scripts/audit_chunks.py`

**機能**:
- 特定キーワード（デフォルト: 強盗）を含むチャンクを検索
- 前後context_n件のチャンクも含めて詳細表示
- 他キーワード（万引き、詐欺等）の混在をチェック
- 結果を `docs/REPORT_chunk_audit.md` に出力

**使用方法**:
```bash
cd backend
source .venv/bin/activate

# 基本実行
python scripts/audit_chunks.py --keyword 強盗 --context-n 1

# オプション指定
python scripts/audit_chunks.py \
  --source "sample3.txt" \
  --keyword 強盗 \
  --context-n 2 \
  --output ../docs/REPORT_chunk_audit.md

# 結果確認
cat ../docs/REPORT_chunk_audit.md
```

### 2. チャンク分割の改善（見出し境界を尊重）

**修正ファイル**: `backend/app/docs/chunker.py`

**変更内容**:
- `chunk_document()` 関数を改修
- 見出し（`##`, `###`）が来たら、chunk_sizeに達していなくても強制的に切る
- overlapは見出しをまたがない（見出しの直前で終了）
- 見出しがない場合は従来通り固定長で切る

**改善前の問題**:
```
チャンク1 (773文字):
# 防犯・犯罪トラブル対応マニュアル
## 第2部：万引き・強盗・詐欺・警察対応編
---
## 1. 万引き・不当持ち出しへの対応
...
## 2. 強盗・暴力事件への対応
...
```
→ 強盗と万引きが同一チャンク内に混在

**改善後の期待**:
```
チャンク1 (300文字):
# 防犯・犯罪トラブル対応マニュアル

チャンク2 (400文字):
## 第2部：万引き・強盗・詐欺・警察対応編
---
## 1. 万引き・不当持ち出しへの対応
...

チャンク3 (400文字):
## 2. 強盗・暴力事件への対応
...
```
→ 各セクションが別チャンクに分離

### 3. /ask自動回帰テストの追加

**新規ファイル**: `backend/test_ask_citations.py`

**テスト内容**:
1. **強盗の質問テスト**:
   - 質問: "強盗への対応方法を教えてください"
   - 期待: 
     - citations が最低1件以上返される
     - 上位の citation に「強盗」または強盗関連語（凶器、110番等）が含まれる
     - 「万引き」のみの citation が優先されない

2. **防災の質問テスト**（回帰確認）:
   - 質問: "防災対策で重要なことは？"
   - 期待: 答えと引用が正常に返される

**使用方法**:
```bash
cd backend
source .venv/bin/activate
python test_ask_citations.py
```

**期待出力**:
```
=== /ask 回帰テスト: 強盗の質問 ===
...
✅ 成功: 強盗関連の引用が含まれています
✅ 成功: 最上位の引用は適切です

=== /ask 回帰テスト: 防災の質問 ===
...
✅ 成功: 引用が返されました

==================================================
 テスト結果サマリー
==================================================
✅ PASS: 強盗の質問
✅ PASS: 防災の質問

🎉 全テストが成功しました！
```

### 4. ドキュメント更新

**更新ファイル**: `README.md`

**追加内容**:
- ## テスト実行セクションを追加
- チャンク監査の実行方法
- /ask回帰テストの実行方法

---

## 再テスト手順

### ステップ1: ChromaDB再構築

```bash
# ChromaDBを削除
rm -rf backend/.chroma

# サーバーを起動（自動的にインデックスが再構築される）
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000 --log-level info
```

サーバーログで以下を確認:
```
INFO: ChromaDB initialized
INFO: Building index...
INFO: Index built successfully, total chunks: XX
```

### ステップ2: チャンク監査実行

別のターミナルで:
```bash
cd backend
source .venv/bin/activate
python scripts/audit_chunks.py --keyword 強盗 --context-n 1

# 結果確認
cat ../docs/REPORT_chunk_audit.md
```

**期待結果**:
- ⚠️ 他キーワード（万引き/詐欺）と混在: **0件** ← 改善前は1件
- ✅ 結論: チャンクは適切に分離されています

### ステップ3: /ask回帰テスト実行

```bash
cd backend
source .venv/bin/activate
python test_ask_citations.py
```

**期待結果**:
```
✅ PASS: 強盗の質問
✅ PASS: 防災の質問
🎉 全テストが成功しました！
```

### ステップ4: 手動確認（オプション）

```bash
# 強盗の質問
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"強盗への対応方法を教えてください"}' \
| jq '.citations[] | {source, quote_preview: (.quote[:80])}'

# 期待: 強盗関連の引用が上位に来る

# Quiz生成（citationsが空にならないことを確認）
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{"level":"beginner","count":1,"source_ids":["sample.txt"],"save":false,"debug":true}' \
| jq '{quizzes_count, first_citations_count: .quizzes[0].citations|length}'

# 期待: first_citations_count >= 1
```

---

## 現状のチャンク設定

**ファイル**: `backend/app/docs/chunker.py`

```python
CATEGORY_SETTINGS: dict[Category, Tuple[int, int]] = {
    "FAQ": (400, 40),      # chunk_size, chunk_overlap
    "一般": (800, 80),
    "技術": (1000, 180),
    "長文": (1300, 250),
}
```

**カテゴリ判定**:
- FAQ: < 1200文字
- 一般: 1200-7999文字
- 技術: 8000-19999文字
- 長文: >= 20000文字

**チャンク戦略**:
1. 見出し（`##`, `###`）があれば優先的に切る
2. 見出しがない場合は固定長で切る
3. overlapは見出しをまたがない

---

## 成果物一覧

### 新規作成
1. ✅ `backend/scripts/audit_chunks.py`: チャンク詳細監査スクリプト
2. ✅ `backend/test_ask_citations.py`: /ask自動回帰テスト
3. ✅ `docs/IMPLEMENTATION_SUMMARY_chunk_citation_fix.md`: 本ドキュメント

### 修正
1. ✅ `backend/app/docs/chunker.py`: チャンク分割改善（見出し境界で切る）
2. ✅ `README.md`: テスト実行手順を追加

### 既存（前回作成）
1. `backend/scripts/audit_chunking.py`: 基本的なチャンク監査（統計情報）
2. `docs/REPORT_rootfix_chunk_and_citations.md`: 根本原因調査レポート

---

## トラブルシューティング

### サーバー起動エラー: `ModuleNotFoundError: No module named 'app'`

**原因**: ディレクトリが間違っている（`backend/backend`等）

**解決**:
```bash
cd /Users/yutakoyanagi/rag-quiz-app/backend
python -m uvicorn app.main:app --reload --port 8000
```

### サーバー起動エラー: `No module named uvicorn`

**原因**: 仮想環境がアクティブになっていない

**解決**:
```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

### チャンクが0件

**原因**: ChromaDBが再構築されていない、またはサーバーが起動していない

**解決**:
1. サーバーが起動していることを確認
2. サーバーログで "Index built successfully" を確認
3. それでも0件なら、`rm -rf backend/.chroma` してサーバー再起動

---

## 次のステップ（将来の改善案）

### オプションA: chunk_sizeの縮小

現在の「一般」カテゴリ（800文字）をさらに縮小:
```python
"一般": (400, 40),  # 800 → 400
```

**効果**: より細かいチャンク分割で、トピック混在がさらに減少

**リスク**: チャンク数が増加し、検索が遅くなる可能性

### オプションB: 設定のパラメータ化

`settings.py` にチャンク設定を追加:
```python
ask_chunk_size: int = Field(default=400, alias="ASK_CHUNK_SIZE")
ask_chunk_overlap: int = Field(default=40, alias="ASK_CHUNK_OVERLAP")
```

**効果**: 環境変数で調整可能になる

### オプションC: RecursiveCharacterTextSplitterの導入

LangChainの`RecursiveCharacterTextSplitter`を使用:
```python
separators = ["\n## ", "\n### ", "\n1.", "\n1.1", "\n\n", "\n", " ", ""]
```

**効果**: より高度な分割ロジック

---

## 関連ドキュメント

- `docs/REPORT_rootfix_chunk_and_citations.md`: 根本原因調査レポート
- `docs/REPORT_chunk_audit.md`: チャンク監査結果（実行後に生成）
- `docs/05_進捗確認.md`: 進捗管理
- `README.md`: プロジェクト全体のドキュメント
