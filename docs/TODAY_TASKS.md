# 本日のタスク（2026-01-22）

## 🎯 優先度：高（必須）

### 1. インデックス再構築 ⚠️ 重要
**目的**: チャンキング改善とキーワード検索精度向上の変更を反映する

**背景**:
- チャンキング改善（PDF見出し検出、サブセクション統合）が実装済み
- キーワード検索精度向上（重要キーワード抽出とスコアリング強化）が実装済み
- しかし、古いインデックスが使われている可能性がある

**手順**:
```bash
# 1. サーバーを停止（Ctrl+C）

# 2. ChromaDBを削除
rm -rf backend/.chroma

# 3. サーバーを起動（起動時に自動的にインデックスが再構築される）
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000 --log-level info

# 4. ログ確認（以下が表示されることを確認）
# "RAGインデックス作成完了: doc_count=X, chunk_count=Y"
# "Chroma投入チャンクのsource分布: {...}"
```

**確認方法**:
```bash
# 1. ヘルスチェック
curl http://localhost:8000/health

# 2. 強盗の質問でcitationsを確認
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"強盗が来たらどうしたらいいですか？", "debug": true}' | jq '.citations[].source, .citations[].quote'

# 期待結果:
# - citations[].source に適切なファイル名が含まれる
# - citations[].quote が50文字以上（見出しだけのチャンクが除外されている）
# - debug.keyword_hits_count が適切な値（重要キーワード「強盗」が検出されている）
```

**完了条件**:
- [ ] インデックス再構築が完了
- [ ] 強盗の質問で適切なcitationsが返る
- [ ] 見出しだけのcitationが返らない
- [ ] 重要キーワードが正しく検出されている

---

### 2. プロンプト改善の効果確認
**目的**: 否定文がrejectされないことを確認する

**背景**:
- プロンプトを改善して肯定文のみ生成するように指示を強化済み
- しかし、改善後も問題が続く可能性がある

**手順**:
```bash
# 1. クイズ生成を実行（複数回）
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "source_ids": ["sample.txt"],
    "save": true,
    "debug": true
  }' | jq '.debug.rejected_items, .debug.stats.llm_negative_rejected_count'

# 2. ログで確認
# - rejected_items に "llm_negative_phrase" が含まれていないか確認
# - llm_negative_rejected_count が 0 に近いか確認
```

**確認項目**:
- [ ] rejected_items に "llm_negative_phrase" が含まれない
- [ ] llm_negative_rejected_count が 0 または非常に少ない
- [ ] accepted_count が target_count（5問）に近い

**問題が続く場合の対応**:
- LLM出力を後処理で肯定文に変換する処理を実装
- または、プロンプトに具体例を追加

---

### 3. 5問生成時のタイムアウト発生率を監視
**目的**: クイズ生成数を5問に変更した影響を確認する

**背景**:
- バックエンドの制限を3問→5問に変更済み
- 5問生成時のタイムアウト発生率を監視する必要がある

**手順**:
```bash
# 1. 複数回クイズ生成を実行（各難易度で3回ずつ）
for level in beginner intermediate advanced; do
  for i in 1 2 3; do
    echo "=== $level (試行 $i) ==="
    time curl -X POST http://localhost:8000/quiz/generate \
      -H "Content-Type: application/json" \
      -d "{
        \"level\": \"$level\",
        \"count\": 5,
        \"source_ids\": [\"sample.txt\"],
        \"save\": false,
        \"debug\": true
      }" | jq '.quizzes | length, .debug.generation.elapsed_ms'
    sleep 5
  done
done
```

**確認項目**:
- [ ] タイムアウトが発生しない（120秒以内に完了）
- [ ] quizzes.length が 5 になる
- [ ] generation.elapsed_ms が許容範囲内（例: 60秒以内）

**問題が発生した場合の対応**:
- LLMパラメータを調整（num_predict, temperature等）
- または、生成数を3問に戻す

---

## 🔶 優先度：中（推奨）

### 4. LLM出力の後処理改善（検討）
**目的**: citations形式の正規化と否定文の肯定文変換を実装する

**背景**:
- LLMがcitationsを正しい形式で返さない場合がある
- LLMが否定文を生成してrejectされる場合がある

**実装内容**:
1. **citations形式の正規化**:
   - `backend/app/quiz/parser.py` に正規化処理を追加
   - 形式エラー時は自動的に正しい形式に変換

2. **否定文の肯定文変換**:
   - `backend/app/quiz/generator.py` に変換処理を追加
   - 「してはならない」→「必ず【逆の行為】を行う」に変換

**実装タイミング**:
- タスク2（プロンプト改善の効果確認）で問題が続く場合に実装

---

### 5. クイズセットのタイトル改善
**目的**: より詳細なタイトルを自動生成する

**背景**:
- 現在は「Quiz Set (初級)」のような自動生成のみ
- ファイル名と難易度からより詳細なタイトルを生成できる

**実装内容**:
- `backend/app/routers/quiz.py` のタイトル生成ロジックを改善
- 例: 「Quiz Set (初級)」→「sample.txt - 初級 - 2026-01-22 10:30」

**実装タイミング**:
- 優先度は中（UX改善のため）

---

## 🔷 優先度：低（将来対応）

### 6. データベースへの移行検討
**目的**: クイズセットの永続化をJSONファイルからデータベースに移行

**背景**:
- 現在はJSONファイルベースの永続化
- 大量のクイズセットが生成された場合の管理が課題

**検討事項**:
- SQLiteへの移行
- または、クイズセットの自動削除機能（古いものから削除）

**実装タイミング**:
- 大量のクイズセットが生成されるようになったら検討

---

### 7. パフォーマンス改善
**目的**: クイズ生成の高速化

**背景**:
- クイズ生成に20〜30秒かかることがある
- LLMの推論時間が主な原因

**検討事項**:
- より高速なLLMモデルの使用
- または、クイズ生成を非同期処理にして、バックグラウンドで生成

**実装タイミング**:
- ユーザーからの要望があったら検討

---

## 📋 チェックリスト

### 作業開始時
- [ ] `git remote -v` でリモート確認
- [ ] `git pull origin main` で最新取得
- [ ] 今日やることを把握

### コード生成前（必要に応じて）
- [ ] 目的を理解したか？
- [ ] 入力/出力は明確か？
- [ ] 不明点は質問したか？

### コミット前（必要に応じて）
- [ ] コードは動作するか？
- [ ] 命名規則に従っているか？
- [ ] 適切なブランチにいるか？（ai-generatedブランチで作業）

---

## 📝 メモ

### 完了したタスク
- ✅ クイズ生成数を5問に変更（2026-01-22）
- ✅ 進捗確認ドキュメントの更新（2026-01-22）
- ✅ 新人フルスタック開発者向けルールの追加（2026-01-22）

### 次回のタスク候補
- インデックス再構築後のQA品質確認
- プロンプト改善の効果が不十分な場合の後処理実装
- クイズセット機能のUX改善

---

_最終更新: 2026-01-22_
