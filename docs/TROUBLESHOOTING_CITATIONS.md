# 根拠が見つからない問題のトラブルシューティング

## 症状
- QAやQuizで根拠（citations）が0件になる
- エラーメッセージ: "引用が見つかりませんでした"

## 確認事項

### 1. インデックスの状態確認

```bash
cd backend
source .venv/bin/activate
python scripts/check_index.py
```

**期待される結果**:
- ChromaDBのチャンク数: 48件以上
- chunk pool内のsource数: 5件
- chunk pool内の総ID数: 48件以上

### 2. ドキュメントの読み込み確認

```bash
cd backend
source .venv/bin/activate
python -c "from app.docs.loader import load_documents; from app.core.settings import settings; docs = load_documents(settings.docs_dir); print(f'読み込まれたドキュメント数: {len(docs)}'); sources = set(doc.source for doc in docs); print(f'ソースファイル: {sorted(sources)}')"
```

**期待される結果**:
- 読み込まれたドキュメント数: 16件以上
- ソースファイル: 5ファイル（sample.txt, sample2.txt, sample3.txt, 清掃マニュアル（サンプル：小売店）.pdf, 防犯・災害対応マニュアル（サンプル）.pdf）

### 3. Quiz用retrievalのテスト

```bash
cd backend
source .venv/bin/activate
python -c "
from app.quiz.retrieval import retrieve_for_quiz
from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore

collection = get_vectorstore(settings.chroma_dir)
citations, debug_info = retrieve_for_quiz(
    source_ids=None,
    level='beginner',
    count=3,
    debug=True
)
print(f'取得されたcitations数: {len(citations)}')
if debug_info:
    for key, value in debug_info.items():
        print(f'{key}: {value}')
"
```

**期待される結果**:
- 取得されたcitations数: 3件以上
- quiz_pool_size: 48件以上
- quiz_final_citations_count: 3件以上

## よくある原因と対処法

### 原因1: インデックスが構築されていない

**症状**: ChromaDBのチャンク数が0件

**対処法**:
```bash
cd backend
source .venv/bin/activate
python scripts/build_index.py --force
```

### 原因2: chunk poolが空

**症状**: chunk pool内のsource数が0件

**対処法**:
- サーバーを再起動（chunk poolは起動時に自動構築される）
- または、`get_pool(collection, force_rebuild=True)` を実行

### 原因3: chunk_selectorが適切なchunkを選べていない

**症状**: citations数が0件、または非常に少ない

**原因**:
- `chunk_selector`はlevel別のキーワードマッチングに依存している
- ドキュメントに該当するキーワードが含まれていない場合、スコアが低くなる

**対処法**:
1. ドキュメントの内容を確認（キーワードが含まれているか）
2. `chunk_selector`のキーワード設定を調整（`backend/app/quiz/chunk_selector.py`）
3. または、`chunk_selector`のスコアリングロジックを緩和

### 原因4: ドキュメントが短すぎる

**症状**: `sample3.txt`などが5行しかない

**対処法**:
- ドキュメントに十分な内容を追加する
- または、短いドキュメントでもスコアが高くなるように`chunk_selector`を調整

### 原因5: source名のUnicode正規化の問題

**症状**: source_idsを指定しても見つからない

**原因**:
- macOSではファイル名がNFD形式、LinuxではNFC形式
- `chunk_pool`はNFC正規化を使用しているが、指定されたsource_idsがNFD形式の場合、マッチしない

**対処法**:
- `retrieve_for_quiz`内でsource_idsをNFC正規化しているが、それでも問題がある場合は手動で正規化

## デバッグ方法

### ログレベルの確認

サーバー起動時に以下のログが出力されることを確認:
```
[ChunkPool] build完了: 5 sources, total_ids=48
[QuizRetrieval] citations作成完了: X件, XXXms
```

### debugモードの使用

Quiz生成時に`debug=true`を指定:
```json
{
  "level": "beginner",
  "count": 3,
  "debug": true
}
```

レスポンスの`debug`フィールドに以下が含まれる:
- `quiz_pool_sources`: pool内のsource一覧
- `quiz_pool_size`: pool内の総ID数
- `quiz_sample_n`: サンプル数
- `quiz_selected_n`: 選択されたchunk数
- `quiz_final_citations_count`: 最終的なcitations数
- `quiz_retrieval_retry_count`: 再取得回数

## 次のステップ

1. 上記の確認事項を実行
2. ログを確認して問題箇所を特定
3. 必要に応じて`chunk_selector`や`retrieve_for_quiz`のロジックを調整
