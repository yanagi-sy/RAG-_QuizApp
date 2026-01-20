# Quiz 教材サンプリング実装 - 完了報告

## 実装日
2026-01-20

## 実装完了 ✅

Quiz を「検索ベース」から「教材サンプリングベース」に完全移行しました。

---

## 達成された目標

### ✅ 全資料 / 全難易度で citations >= 3 件を保証
直接テスト結果（Python スクリプト）:
```
✓ sample.txt / beginner, intermediate, advanced → 4 citations
✓ sample2.txt / beginner, intermediate, advanced → 5 citations
✓ sample3.txt / beginner, intermediate, advanced → 3 citations
✓ 防犯・安全ナレッジベース.pdf / 全難易度 → 4 citations
✓ 店舗運営ナレッジベース.pdf / 全難易度 → 4 citations

合格率: 15/15 (100%)
```

### ✅ /ask は無影響
- `/ask` のコードは一切変更なし
- 回帰テストOK

### ✅ 難易度が確実に効く
- 検索クエリではなく「段落選択ルール」で実装
- beginner: 概要/定義/基本
- intermediate: 手順/方法/操作
- advanced: 例外/禁止/注意

### ✅ 堅牢性の確保
- バッチ取得（全件一括を避ける）
- thread-safe（並列アクセス対応）
- Unicode正規化（macOS NFD対策）

---

## 実装ファイル

### 新規作成
1. `backend/app/quiz/chunk_pool.py` - Chunk Pool（sourceごとのID管理）
2. `backend/app/quiz/chunk_selector.py` - 難易度別スコアリング
3. `backend/app/quiz/retrieval.py` - サンプリングベースの retrieval

### 変更
4. `backend/app/routers/quiz.py` - 薄型化（search_query 依存削除）
5. `backend/app/core/settings.py` - Quiz専用パラメータ追加

### テストスクリプト
6. `backend/test_retrieval.py` - retrieval ロジックのテスト
7. `backend/test_all_combinations.py` - 全資料 / 全難易度のテスト

### ドキュメント
8. `docs/07_Quiz教材サンプリング実装.md` - 詳細実装記録

---

## 動作確認方法

### 1. retrieval ロジックの直接テスト
```bash
cd backend
source .venv/bin/activate
python test_all_combinations.py
```

期待結果: 全ての組み合わせで `✓` が表示される

### 2. API 経由でのテスト（debug情報確認）
```bash
curl -s -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{"level":"beginner","count":5,"source_ids":["sample2.txt"],"debug":true}' \
  | jq '.debug | {pool_sources, pool_size, sample_n, selected_n, citations_count}'
```

期待結果:
```json
{
  "pool_sources": ["sample2.txt"],
  "pool_size": 5,
  "sample_n": 20,
  "selected_n": 5,
  "citations_count": 5
}
```

---

## 既知の問題（今回のタスク範囲外）

### LLM の JSON 出力の不安定性
- **現象**: LLM が不正な JSON を出力（全角引用符など）し、パースエラーが発生
- **影響**: quiz 生成が 0 件になるケースがある
- **原因**: LLM モデル（Ollama/llama3）の出力品質
- **対策**: 今回の実装とは無関係。以下のいずれかで解決可能:
  1. LLM モデルの変更（Gemini など JSON 出力が安定したモデル）
  2. JSON スキーマバリデーションの強化
  3. LLM プロンプトの改善

**重要**: retrieval（citations取得）は 100% 成功しています。問題は LLM の JSON 生成のみです。

---

## 設定パラメータ（追加）

### Quiz専用サンプリング設定
`backend/app/core/settings.py` に以下を追加:

```python
quiz_pool_max_ids_per_source: int = 3000  # 1sourceあたりの最大保持ID数
quiz_pool_batch_size: int = 5000          # Chroma collection.get() のバッチサイズ
quiz_sample_multiplier: int = 4           # サンプル数の倍率（sample_n = count * multiplier）
quiz_sample_min_n: int = 20               # サンプル数の最小値
quiz_citations_min: int = 3               # 最低引用数（これ以下なら再取得）
```

環境変数で上書き可能:
```bash
export QUIZ_POOL_MAX_IDS_PER_SOURCE=5000
export QUIZ_SAMPLE_MULTIPLIER=6
```

---

## まとめ

### 成果
- ✅ Quiz を「検索ベース」から「教材サンプリングベース」に完全移行
- ✅ 全資料 / 全難易度で必ず citations >= 3 件を確保
- ✅ /ask は無影響
- ✅ 難易度は「段落選び」で確実に効く
- ✅ バッチ取得、thread-safe、NFC正規化など、堅牢性を確保

### 今後の改善候補
- LLM モデルの変更（Gemini への移行）
- JSON 出力の安定性向上

---

## 関連ドキュメント
- `docs/07_Quiz教材サンプリング実装.md` - 詳細な実装記録
- `docs/06_リファクタリング記録.md` - 以前のリファクタリング記録
- `.cursor/rules/00-minimum.mdc` - 開発方針
- `.cursor/rules/10-naming.mdc` - 命名規則
