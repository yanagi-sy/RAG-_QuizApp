# 根拠が見つからない問題の修正

## 問題の原因

`/ask` APIで根拠（citations）が0件になる問題が発生していました。

### 診断結果

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"強盗が来たらどうしたらいいですか？","debug":true}'
```

**結果**:
- `collection_count`: 48（インデックスは存在）
- `semantic_hits_count`: 20（意味検索で20件見つかった）
- `keyword_hits_count`: 14（キーワード検索で14件見つかった）
- `merged_count`: 26（マージ後26件）
- `post_rerank_count`: 8（リランク後8件）
- **`after_threshold_count`: 0（閾値フィルタ後0件）** ← 問題箇所
- **`final_citations_count`: 0（最終的に0件）**
- `zero_reason`: "all_candidates_removed_by_rerank_threshold"

### 原因

リランク後のスコアが全て閾値以下になっていました：

- 最高スコア: **-1.9199**
- 設定されている閾値: **-1.5**（デフォルト）
- `-1.9199 < -1.5` なので、**全ての候補が除外**されていた

## 修正内容

`backend/app/core/settings.py` の `rerank_score_threshold` を緩和：

```python
# 修正前
rerank_score_threshold: float = Field(
    default=-1.5,
    ...
)

# 修正後
rerank_score_threshold: float = Field(
    default=-2.5,  # -1.5 → -2.5 に緩和
    ...
)
```

## 確認方法

### 1. 設定の確認

```bash
cd backend
source .venv/bin/activate
python -c "from app.core.settings import settings; print(f'rerank_score_threshold: {settings.rerank_score_threshold}')"
```

期待される結果: `rerank_score_threshold: -2.5`

### 2. APIテスト

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"強盗が来たらどうしたらいいですか？","debug":true}' \
| jq '.debug | {after_threshold_count, final_citations_count, zero_reason}'
```

期待される結果:
- `after_threshold_count`: 1以上
- `final_citations_count`: 1以上
- `zero_reason`: null または存在しない

### 3. 環境変数での上書き（オプション）

`.env` ファイルで上書き可能：

```bash
# backend/.env
RERANK_SCORE_THRESHOLD=-2.5
```

## 補足

### 他の閾値設定

必要に応じて、以下の設定も調整可能：

- `rerank_score_gap_threshold`: トップスコアとの差分閾値（デフォルト: 6.0）
  - 最高スコアと最低スコアの差分が大きい場合に調整

### パフォーマンスへの影響

- 閾値を緩和すると、より多くの候補が通過する
- 品質が若干低下する可能性があるが、根拠が見つからないよりは良い
- 必要に応じて、`rerank_score_gap_threshold` で相対的な品質管理を行う

## 関連ファイル

- `backend/app/core/settings.py`: 設定定義
- `backend/app/routers/ask.py`: `/ask` APIの実装
- `backend/app/rag/hybrid_retrieval.py`: ハイブリッド検索の実装
