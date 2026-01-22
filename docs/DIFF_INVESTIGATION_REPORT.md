# 差分調査レポート（2026-01-22）

## 0. まとめ（結論先出し）

- **起動失敗の直接原因**: `backend/app/routers/quiz.py` が `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` を `app.schemas.quiz` からimportしようとしているが、HEAD（コミット済み）の `backend/app/schemas/quiz.py` にはこれらのクラスが定義されていない
- **直接原因を生んだ差分**: コミット `d65ccb6` で `routers/quiz.py` に `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportが追加されたが、対応する `schemas/quiz.py` の変更がコミットされていない（作業ツリーにのみ存在）
- **最短の復旧策**:
  1. **推奨**: 作業ツリーの `backend/app/schemas/quiz.py` の変更をコミットする（`QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` の定義が含まれている）
  2. 代替案: `routers/quiz.py` から `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportを一時的に削除し、関連するエンドポイントをコメントアウト
  3. 代替案: `d65ccb6` より前のコミット（`f479060`）に戻す（`QuizSet` 関連機能が存在しない状態）

## 1. 現状スナップショット

### Git状態
- **branch**: `master`
- **HEAD**: `2f30bc953e7cdc0f8bb21959e613c0cb24c08cc6`
- **最新コミット**: `feat: チャンク分割改善 + Citations品質テスト追加`
- **git status**: 
  - `backend/app/schemas/quiz.py` が未コミット（M）
  - `backend/app/routers/quiz.py` はコミット済み（変更なし）
  - その他、`.venv` 内の `__pycache__` ファイルが多数変更されている（無視可能）

### エラーログ（要点）
- **エラーメッセージ**: `ImportError: cannot import name 'QuizSetMetadata' from 'app.schemas.quiz'`
- **発生箇所**: `backend/app/routers/quiz.py` の11-19行目のimport文
- **エラー発生タイミング**: uvicorn起動時（`app.main` が `app.routers.quiz` をimportする際）

### QuizSet* の存在確認結果
- **作業ツリー（未コミット）**: `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` が存在する
  ```bash
  $ python -c "import app.schemas.quiz as q; print([n for n in dir(q) if 'QuizSet' in n])"
  ['QuizSet', 'QuizSetListResponse', 'QuizSetMetadata']
  ```
- **HEAD（コミット済み）**: `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` が存在しない
  ```bash
  $ git show HEAD:backend/app/schemas/quiz.py | grep -A 5 "class QuizSet"
  QuizSet not found in HEAD
  ```

## 2. "前（正常）"の特定根拠

### どのコミットを GOOD としたか
- **候補1**: `d65ccb6` (`fix: Parser改修でLLM出力を機械的に安定化`)
  - `routers/quiz.py` に `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportが追加されている
  - しかし、`schemas/quiz.py` にはこれらのクラスが存在しない
  - **結論**: このコミットでも起動できない可能性が高い

- **候補2**: `f479060` (`feat: Quiz MVP版（3問固定）+ タイムアウト対策 + LLM負担計測`)
  - `routers/quiz.py` に `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportが存在しない
  - **結論**: このコミットでは起動できる可能性が高い（`QuizSet` 関連機能が存在しないため）

### GOOD で起動確認できた証拠
- **検証方法**: worktree作成を試みたが、sandbox制限により失敗
- **代替検証**: `git show` で確認した結果、`f479060` では `routers/quiz.py` に `QuizSet` 関連のimportが存在しない
- **推測**: `f479060` では起動できるが、`d65ccb6` 以降は起動できない状態

## 3. 主要差分（ファイル別）

### quiz.py router 差分（import行の変化）

**d65ccb6 と HEAD の比較**:
- `routers/quiz.py` のimport文は同一（差分なし）
- 両方とも以下のimportを含んでいる:
  ```python
  from app.schemas.quiz import (
      QuizRequest,
      QuizResponse,
      QuizGenerateRequest,
      QuizGenerateResponse,
      QuizSetMetadata,      # ← これが問題
      QuizSet,               # ← これが問題
      QuizSetListResponse,   # ← これが問題
  )
  ```

**f479060 との比較**:
- `f479060` では `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportが存在しない
- `d65ccb6` で追加された

### schemas/quiz.py 差分（クラス定義の有無）

**HEAD（コミット済み）の状態**:
- 85行
- `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` が存在しない
- `QuizGenerateResponse` に `quiz_set_id` フィールドが存在しない
- `QuizGenerateRequest` に `save` フィールドが存在しない

**作業ツリー（未コミット）の状態**:
- 117行（32行の追加）
- `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` が存在する
- `QuizGenerateResponse` に `quiz_set_id` フィールドが追加されている
- `QuizGenerateRequest` に `save` フィールドが追加されている

**差分の要点**:
```diff
+ class QuizSetMetadata(BaseModel):
+     """クイズセットメタデータ（一覧用）"""
+     id: str = Field(..., description="セットID")
+     title: str = Field(..., description="セットタイトル")
+     difficulty: Level = Field(..., description="難易度")
+     created_at: str = Field(..., description="作成日時（ISO形式）")
+     question_count: int = Field(..., description="問題数")
+
+ class QuizSet(BaseModel):
+     """クイズセット"""
+     id: str = Field(..., description="セットID")
+     title: str = Field(..., description="セットタイトル")
+     difficulty: Level = Field(..., description="難易度")
+     created_at: str = Field(..., description="作成日時（ISO形式）")
+     quizzes: list[QuizItem] = Field(..., description="問題リスト")
+
+ class QuizSetListResponse(BaseModel):
+     """クイズセット一覧レスポンス"""
+     quiz_sets: list[QuizSetMetadata] = Field(..., description="セットメタデータリスト")
+     total: int = Field(..., description="総件数")
```

### main.py 差分（router include の有無）
- `main.py` に差分なし
- `app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])` は両方の状態で存在

## 4. 原因の推定（根拠付き）

### なぜ ImportError になったか

Pythonのimportの仕組み:
1. `app.main` が起動時に `app.routers.quiz` をimportする
2. `app.routers.quiz` が `from app.schemas.quiz import QuizSetMetadata, QuizSet, QuizSetListResponse` を実行する
3. Pythonは `app.schemas.quiz` モジュールを読み込み、その中から `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` を探す
4. **HEAD（コミット済み）の状態では、これらのクラスが `schemas/quiz.py` に存在しないため、ImportErrorが発生する**

### なぜ今日の作業で起きた可能性が高いか

**タイムラインの推定**:
1. `d65ccb6` で `routers/quiz.py` に `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportが追加された
2. 同時に `schemas/quiz.py` にもこれらのクラス定義が追加された（作業ツリーに存在）
3. しかし、`schemas/quiz.py` の変更がコミットされずに残った
4. その後、`2f30bc9` で他の変更がコミットされたが、`schemas/quiz.py` の変更はコミットされなかった
5. その結果、HEADの状態では `routers/quiz.py` が存在しないクラスをimportしようとしてエラーになる

**根拠**:
- `git log -S "QuizSetMetadata"` で `d65ccb6` が最初に `QuizSetMetadata` を追加したコミットとして検出された
- `d65ccb6` のコミットメッセージには `schemas/quiz.py` の変更が含まれていない（`--stat` で確認）
- 作業ツリーに `schemas/quiz.py` の未コミット変更が存在する

## 5. 復旧オプション（優先度付き）

### Option A: schemas に不足クラスを最小追加（推奨）

**変更箇所**:
- `backend/app/schemas/quiz.py` に `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` を追加
- `QuizGenerateRequest` に `save` フィールドを追加
- `QuizGenerateResponse` に `quiz_set_id` フィールドを追加

**影響範囲**:
- 既存の `routers/quiz.py` のimportが正常に動作する
- `/quiz/sets` エンドポイントが正常に動作する
- 作業ツリーの変更をコミットするだけなので、影響範囲が最小

**メリット/デメリット/作業量**:
- メリット: 既存の機能を維持できる、作業量が最小
- デメリット: なし
- 作業量: 1コマンド（`git add backend/app/schemas/quiz.py && git commit`）

### Option B: quiz router を一時無効化して起動を通す

**変更箇所**:
- `backend/app/routers/quiz.py` から `QuizSetMetadata`, `QuizSet`, `QuizSetListResponse` のimportを削除
- `/quiz/sets` 関連のエンドポイント（3つ）をコメントアウト
- `backend/app/main.py` から `quiz.router` のincludeを一時的にコメントアウト（または条件分岐で無効化）

**影響範囲**:
- `/quiz/sets` エンドポイントが使用不可になる
- `/quiz/generate` の `save` 機能が使用不可になる
- 他の `/quiz` エンドポイントは影響なし

**メリット/デメリット/作業量**:
- メリット: サーバーを即座に起動できる
- デメリット: `QuizSet` 関連機能が使用不可、後で復元が必要
- 作業量: 10-15分（import削除、エンドポイントコメントアウト、テスト）

### Option C: GOODコミットへ戻す

**変更箇所**:
- `f479060` に戻す（`QuizSet` 関連機能が存在しない状態）

**影響範囲**:
- `QuizSet` 関連機能が完全に失われる
- `/quiz/sets` エンドポイントが存在しない
- `/quiz/generate` の `save` 機能が存在しない

**メリット/デメリット/作業量**:
- メリット: 確実に起動できる状態に戻る
- デメリット: `QuizSet` 関連機能の実装が失われる、後で再実装が必要
- 作業量: 1コマンド（`git reset --hard f479060`）だが、機能損失が大きい

## 6. 次のアクション（コマンド付き）

### まずやるコマンド

**Option A（推奨）を実行する場合**:
```bash
# 1. 作業ツリーの変更を確認
cd /Users/yutakoyanagi/rag-quiz-app
git diff backend/app/schemas/quiz.py

# 2. 変更をステージング
git add backend/app/schemas/quiz.py

# 3. コミット
git commit -m "fix: QuizSetMetadata, QuizSet, QuizSetListResponse を schemas/quiz.py に追加"

# 4. 起動確認
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000 --log-level info
```

### 期待される結果

**Option A 実行後**:
- `ImportError` が解消される
- uvicornが正常に起動する
- `/quiz/sets` エンドポイントが正常に動作する
- `/quiz/generate` の `save` 機能が正常に動作する

**確認コマンド**:
```bash
# 起動確認
curl http://127.0.0.1:8000/health

# import確認
python -c "from app.main import app; print('OK')"
```

---

## 補足情報

### 環境情報
- Python: 3.11.9
- pip: 25.3
- uvicorn: 0.40.0
- fastapi: 0.128.0
- pydantic: 2.12.5

### 関連ファイル
- `backend/app/routers/quiz.py`: 268行（HEADと作業ツリーで同一）
- `backend/app/schemas/quiz.py`: HEAD=85行、作業ツリー=117行
- `backend/app/main.py`: 72行（差分なし）
- `backend/app/quiz/store.py`: QuizSet保存機能の実装（HEADと作業ツリーで同一）

### コミット履歴（関連）
- `2f30bc9` (HEAD): `feat: チャンク分割改善 + Citations品質テスト追加`
- `d65ccb6`: `fix: Parser改修でLLM出力を機械的に安定化` ← `QuizSetMetadata` import追加
- `f479060`: `feat: Quiz MVP版（3問固定）+ タイムアウト対策 + LLM負担計測` ← `QuizSet` 機能なし
