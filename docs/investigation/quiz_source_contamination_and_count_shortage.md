# クイズ生成におけるソース混入と規定数未達の原因調査レポート

## 1. 概要

本レポートは、rag-quiz-appのクイズ生成機能において観測される以下の2つの問題について、コード分析とログ調査に基づいて原因を特定することを目的とする。

### 調査対象問題

1. **選択したファイル以外の文言がクイズに入り込む現象**
   - 単一ソース（例：`sample3.txt`）を指定しているにもかかわらず、他のファイル（例：`防犯・災害対応マニュアル（サンプル）.pdf`）の内容がクイズのstatementやcitationに含まれる

2. **クイズが規定数生成されない現象**
   - `count=5`を指定しているにもかかわらず、5問に達しない（例：3問のみ生成される）
   - 生成時間が長い（例：60秒以上）

### 調査日時

- **調査日**: 2026-01-23
- **対象バージョン**: 最新のmasterブランチ

---

## 2. 問題1: 選択したファイル以外の文言がクイズに入り込む現象

### 2.1 観測される症状

- `source_ids=["sample3.txt"]`を指定しているにもかかわらず、クイズのstatementに「火災」「避難」「災害」などのキーワードが含まれる
- citationのsourceが`防犯・災害対応マニュアル（サンプル）.pdf`になっている
- ログに「【重大】選択されたcitationのsourceが不一致」が出力される

### 2.2 原因分析

#### 原因1: chunk_poolでのsourceフィルタリングの不備

**発生箇所**: `backend/app/quiz/chunk_pool.py::sample_ids_multi_source()`

**問題点**:
- `sample_ids_multi_source()`は指定されたsource_idsからサンプルするが、Unicode正規化（NFC）の不一致でマッチしない可能性がある
- poolのキーと指定されたsource_idsの正規化が一致しない場合、空のリストが返される
- しかし、エラーハンドリングが不十分で、空リストが返された場合の処理が不適切

**コード箇所**:
```python
# chunk_pool.py:222-248
target_sources_norm = [unicodedata.normalize("NFC", s) for s in sources]
pool_keys_norm = {unicodedata.normalize("NFC", k): k for k in pool.keys()}
target_sources = []

for source_norm in target_sources_norm:
    matched_key = pool_keys_norm.get(source_norm)
    if matched_key:
        target_sources.append(matched_key)
    else:
        # エラーログは出力するが、空リストを返すだけ
        logger.error(f"[ChunkPool] 【重大】指定されたsourceがpoolに存在しません")
```

**影響**:
- 指定されたsourceがpoolに存在しない場合、空のリストが返される
- しかし、`retrieval.py`では空リストの場合にエラーを返すが、その後の処理で他のsourceからサンプルする可能性がある

#### 原因2: retrieval.pyでのフィルタリング後の再サンプリング

**発生箇所**: `backend/app/quiz/retrieval.py::retrieve_for_quiz()`

**問題点**:
- `sample_ids_multi_source()`でサンプルしたIDを取得した後、実際のchunkを取得してからsourceフィルタを適用している
- フィルタ後のchunkが0件の場合、再サンプリングを行うが、この際にsource_ids制約が緩和される可能性がある

**コード箇所**:
```python
# retrieval.py:260-321
while len(citations) < cit_min and retry_count < max_retries:
    retry_count += 1
    # sample_n を増やして再サンプル（指定sourceのみ）
    sample_n = sample_n * 2
    sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
    
    # フィルタ後のchunkが0件の場合、再サンプリング
    # ただし、source_ids制約は維持されているはずだが、実際には他のsourceが混入する可能性がある
```

**影響**:
- 再サンプリング時に、指定source以外のchunkが混入する可能性がある
- 特に、Unicode正規化の不一致で指定sourceがマッチしない場合、他のsourceからサンプルされる可能性がある

#### 原因3: LLMが生成したstatementに他のファイルの内容が含まれる

**発生箇所**: `backend/app/quiz/generator.py::generate_and_validate_quizzes()`

**問題点**:
- LLMは学習データから他のファイルの内容を想起する可能性がある
- プロンプトに渡されたcitationsは指定sourceのものだが、LLMが生成するstatementには他のファイルの内容が含まれる可能性がある
- 特に、プロンプトの例文に「火災」「避難」などのキーワードが含まれている場合、LLMがこれらのキーワードを含むstatementを生成する可能性がある

**コード箇所**:
```python
# generator.py:103-109
ret = build_quiz_generation_messages(
    level=level,
    count=count,
    topic=topic,
    citations=citations,  # 指定sourceのcitations
    banned_statements=banned_statements,
)
```

**影響**:
- LLMが生成するstatementに、指定source以外の内容が含まれる可能性がある
- 特に、プロンプトの例文に他のファイルの内容が含まれている場合、LLMがそれを学習してしまう

#### 原因4: parser.pyでのfallback_citationsの使用

**発生箇所**: `backend/app/quiz/parser.py::_parse_single_quiz()`

**問題点**:
- LLMが返したcitationsが不正形式（int, list, str）の場合、`fallback_citations`を使用する
- `fallback_citations`は`retrieve_for_quiz()`で取得したもので、statement生成前に取得されている
- そのため、statementとfallback_citationsの対応関係が崩れる可能性がある

**コード箇所**:
```python
# parser.py:249-290
# fallback_citations（実際には確定citation）を必ず使用し、最低1件を保証
if fallback_citations and len(fallback_citations) > 0:
    primary_citation = fallback_citations[0]
    
    # 【品質担保】citationのsourceとquoteの内容が一致しているか確認
    fire_keywords = ["火災", "避難", "災害", "防犯"]
    has_fire_content = any(keyword in primary_citation.quote for keyword in fire_keywords)
    
    # sample*.txtファイルに火災関連の内容が含まれている場合は不一致として検出
    if has_fire_content and primary_citation.source.startswith("sample") and primary_citation.source.endswith(".txt"):
        logger.error(f"[PARSE] 【重大】citationのsourceと内容の不一致を検出")
        # このcitationは除外する（誤ったsourceの可能性がある）
```

**影響**:
- fallback_citationsが指定source以外のものの場合、statementと対応しないcitationが付与される可能性がある
- 特に、再サンプリング時に他のsourceが混入した場合、fallback_citationsにも他のsourceが含まれる可能性がある

#### 原因5: generation_handler.pyでのsourceチェックの不備

**発生箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**問題点**:
- citationのsourceをチェックしているが、チェック後にスキップするだけで、エラーを返さない
- そのため、他のsourceのcitationが混入しても処理が続行される

**コード箇所**:
```python
# generation_handler.py:321-344
# 【品質担保】選択されたcitationのsourceが指定ソースと一致することを確認
if expected_source and single_citation.source != expected_source:
    logger.error(f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致")
    # このcitationをスキップ
    continue  # スキップするだけで、エラーを返さない
```

**影響**:
- source不一致のcitationが検出されても、スキップするだけで処理が続行される
- そのため、他のsourceのcitationが混入しても、エラーとして扱われない

### 2.3 根本原因のまとめ

1. **Unicode正規化の不一致**: source_idsとpoolのキーの正規化が一致しない場合、指定sourceがマッチしない
2. **フィルタリングのタイミング**: chunk取得後にフィルタを適用しているため、他のsourceのchunkが混入する可能性がある
3. **LLMの学習データ**: LLMが学習データから他のファイルの内容を想起する可能性がある
4. **fallback_citationsの不整合**: statement生成前に取得したfallback_citationsが、statementと対応していない可能性がある
5. **エラーハンドリングの不備**: source不一致を検出しても、スキップするだけでエラーを返さない

---

## 3. 問題2: クイズが規定数生成されない現象

### 3.1 観測される症状

- `count=5`を指定しているにもかかわらず、3問のみ生成される
- ログに「規定数に達していません: accepted=3, requested=5, shortage=2」が出力される
- 生成時間が長い（例：60秒以上）
- `attempts`が10回以上になる

### 3.2 原因分析

#### 原因1: 重複除外による生成数の減少

**発生箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**問題点**:
- `_is_duplicate()`で重複をチェックしているが、重複が多すぎると目標数に達しない
- 特に、「行う/行わない」の単純反転が重複として検出されない場合、同じ内容のクイズが複数生成される可能性がある
- 連続重複が5回続くと早期終了するが、この時点で目標数に達していない可能性がある

**コード箇所**:
```python
# generation_handler.py:440-468
# statementの重複チェック
if _is_duplicate(selected_quiz.statement, accepted_statements):
    consecutive_duplicates += 1
    logger.warning(f"重複クイズを除外: '{selected_quiz.statement[:50]}...'")
    all_rejected_items.append({
        "statement": selected_quiz.statement[:100],
        "reason": "duplicate_statement",
    })
    continue

# 連続重複が多すぎる場合は早期終了
if consecutive_duplicates >= max_consecutive_duplicates:
    logger.error(f"[GENERATION_RETRY] 連続重複が{consecutive_duplicates}回続いたため、早期終了します")
    break
```

**影響**:
- 重複が多すぎると、目標数に達する前に試行が終了する
- 特に、使用済みcitationsが多くなると、新しいcitationが少なくなり、重複が増える

#### 原因2: 使用済みcitationsのリセットロジックの不備

**発生箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**問題点**:
- 使用済みcitationsを記録しているが、リセットロジックが不適切
- 使用可能なcitationsが少なくなった場合、リセットするが、リセットしても目標数に達しない可能性がある
- 特に、全citations数が目標数より少ない場合、リセットしても意味がない

**コード箇所**:
```python
# generation_handler.py:246-275
if len(available_citations) < remaining and len(accepted_quizzes) < target_count:
    logger.warning(f"[GENERATION_RETRY] 使用可能なcitationsが不足")
    
    # リセットしても意味がない場合は早期終了
    if len(citations) < remaining:
        logger.error(f"[GENERATION_RETRY] 全citations数({len(citations)})が残り必要数({remaining})を下回るため、早期終了します")
        break
    
    # リセットして再試行（ただし、リセット回数を制限）
    if attempts < max_attempts - 1:
        logger.info(f"[GENERATION_RETRY] 使用済みリストをリセット")
        used_citation_keys.clear()
        available_citations = citations
```

**影響**:
- 使用可能なcitationsが少なくなると、リセットしても目標数に達しない可能性がある
- 特に、全citations数が目標数より少ない場合、早期終了する

#### 原因3: バリデーション失敗による生成数の減少

**発生箇所**: `backend/app/quiz/generator.py::generate_and_validate_quizzes()`

**問題点**:
- `validate_quiz_item()`でバリデーションを行っているが、失敗が多いと目標数に達しない
- 特に、`false_generation_failed`や`llm_negative_phrase`などの理由でrejectされる場合が多い

**コード箇所**:
```python
# generator.py:184-193
# 否定語チェック（LLMが勝手に×を作るのを防ぐ）
if _contains_negative_phrase(statement):
    logger.warning(f"LLM由来の否定文を reject: {statement[:50]}")
    rejected.append({
        "statement": statement[:100],
        "reason": "llm_negative_phrase",
    })
    continue

# validator チェック（○）
ok, reason = validate_quiz_item(quiz_dict)
if not ok:
    rejected.append({
        "statement": statement[:100],
        "reason": reason,
    })
    continue
```

**影響**:
- バリデーション失敗が多いと、目標数に達する前に試行が終了する
- 特に、LLMが生成するstatementの品質が低い場合、バリデーション失敗が増える

#### 原因4: 1回のLLM呼び出しで1問のみ生成

**発生箇所**: `backend/app/quiz/generator.py::generate_and_validate_quizzes()`

**問題点**:
- `generate_and_validate_quizzes()`は`count=1`専用で、1回のLLM呼び出しで1問のみ生成する
- 目標5問に達するには、最低5回のLLM呼び出しが必要
- 重複やバリデーション失敗が多いと、LLM呼び出し回数が増える

**コード箇所**:
```python
# generator.py:93-96
# count=1 専用制限（複数問は Router側でループ）
if count > 1:
    logger.warning(f"count={count} が指定されましたが、この関数は count=1 専用です。count=1 に制限します。")
    count = 1
```

**影響**:
- 1回のLLM呼び出しで1問のみ生成するため、効率が悪い
- 目標5問に達するには、最低5回のLLM呼び出しが必要で、時間がかかる

#### 原因5: タイムアウトによる早期終了

**発生箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**問題点**:
- タイムアウトチェックを行っているが、タイムアウト時間が短い場合、目標数に達する前に終了する
- 特に、LLM呼び出しが遅い場合、タイムアウトが発生しやすい

**コード箇所**:
```python
# generation_handler.py:211-218
# タイムアウトチェック
elapsed_time = time.perf_counter() - start_time
if elapsed_time > max_total_time_sec:
    logger.warning(f"[GENERATION_RETRY] タイムアウト: {elapsed_time:.1f}秒経過")
    break
```

**影響**:
- タイムアウトが発生すると、目標数に達する前に終了する
- 特に、LLM呼び出しが遅い場合、タイムアウトが発生しやすい

### 3.3 根本原因のまとめ

1. **重複除外の多さ**: 重複が多すぎると、目標数に達する前に試行が終了する
2. **使用済みcitationsの不足**: 使用可能なcitationsが少なくなると、リセットしても目標数に達しない
3. **バリデーション失敗の多さ**: バリデーション失敗が多いと、目標数に達する前に試行が終了する
4. **1回のLLM呼び出しで1問のみ生成**: 効率が悪く、時間がかかる
5. **タイムアウト**: タイムアウトが発生すると、目標数に達する前に終了する

---

## 4. 改善提案

### 4.1 問題1の改善提案

#### 改善1: Unicode正規化の統一とエラーハンドリングの強化

**概要**:
- source_idsとpoolのキーの正規化を統一する
- マッチしない場合、エラーを返すか、より柔軟なマッチングを行う

**適用箇所**: `backend/app/quiz/chunk_pool.py::sample_ids_multi_source()`

**例**:
```python
# より柔軟なマッチング（部分一致も許容）
for source_norm in target_sources_norm:
    matched_key = None
    # 完全一致を試す
    matched_key = pool_keys_norm.get(source_norm)
    # 完全一致しない場合、部分一致を試す
    if not matched_key:
        for pool_key_norm, pool_key in pool_keys_norm.items():
            if source_norm in pool_key_norm or pool_key_norm in source_norm:
                matched_key = pool_key
                break
    if matched_key:
        target_sources.append(matched_key)
    else:
        # マッチしない場合はエラーを返す
        raise ValueError(f"指定されたsource '{source_norm}' がpoolに存在しません")
```

#### 改善2: フィルタリングのタイミングを早める

**概要**:
- chunk取得前にsourceフィルタを適用する
- または、chunk取得時にsourceフィルタを適用する

**適用箇所**: `backend/app/quiz/retrieval.py::retrieve_for_quiz()`

**例**:
```python
# chunk取得時にsourceフィルタを適用
results = collection.get(
    ids=sampled_ids,
    include=["documents", "metadatas"],
    where={"source": {"$in": source_ids}}  # ChromaDBのwhere条件でフィルタ
)
```

#### 改善3: LLMプロンプトの改善

**概要**:
- プロンプトに「指定されたsourceのみを使用する」という指示を追加する
- 例文から他のファイルの内容を削除する

**適用箇所**: `backend/app/llm/prompt.py::build_quiz_generation_messages()`

**例**:
```python
# プロンプトに追加
user_content += f"\n【重要】指定されたsourceのみを使用してください。"
user_content += f"\n指定source: {citations[0].source if citations else 'N/A'}"
user_content += f"\n他のsourceの内容を含めないでください。"
```

#### 改善4: fallback_citationsの再検索

**概要**:
- statement生成後、statementのキーワードで再検索して根拠を再付与する
- 単一ソース制約を維持する

**適用箇所**: 新規モジュール `backend/app/quiz/citation_matcher.py`

**例**:
```python
def match_citations_for_statement(
    statement: str,
    source_ids: List[str],
    collection: chromadb.Collection
) -> List[Citation]:
    """statementのキーワードで再検索して根拠を再付与"""
    # statementからキーワードを抽出
    keywords = extract_keywords(statement)
    # キーワードで再検索（source_ids制約を維持）
    citations = quiz_retrieve_chunks(
        query=" ".join(keywords),
        source_filter=source_ids,
        k=3
    )
    return citations
```

#### 改善5: source不一致時のエラーハンドリングの強化

**概要**:
- source不一致を検出した場合、エラーを返すか、より厳格にチェックする

**適用箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**例**:
```python
# source不一致を検出した場合、エラーを返す
if expected_source and single_citation.source != expected_source:
    logger.error(f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致")
    # エラーを返す（スキップしない）
    raise ValueError(f"citationのsourceが不一致: expected={expected_source}, actual={single_citation.source}")
```

### 4.2 問題2の改善提案

#### 改善1: 重複判定の強化

**概要**:
- `_normalize_statement()`に否定語除去を追加する
- 「行う/行わない」の単純反転を重複として検出する

**適用箇所**: `backend/app/quiz/generation_handler.py::_normalize_statement()`

**例**:
```python
def _normalize_statement(statement: str) -> str:
    # 否定語除去
    negation_patterns = [r'しない', r'行わない', r'ではない', r'なくてもよい']
    normalized = statement
    for pattern in negation_patterns:
        normalized = re.sub(pattern, '', normalized)
    # 既存の正規化処理
    normalized = re.sub(r'\s+', '', normalized)
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    return normalized.lower()
```

#### 改善2: 使用済みcitationsのリセットロジックの改善

**概要**:
- リセットロジックを改善し、より効率的にcitationsを再利用する

**適用箇所**: `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`

**例**:
```python
# リセットロジックを改善
if len(available_citations) < remaining:
    # リセットする前に、使用済みcitationsのうち、重複が少ないものを再利用
    # または、citationsを増やす（retrieval.pyで再取得）
    if attempts < max_attempts - 1:
        # citationsを再取得（retrieval.pyを呼び出す）
        citations, _ = retrieve_for_quiz(
            source_ids=request.source_ids,
            level=request.level,
            count=target_count * 2,  # 多めに取得
            debug=request.debug
        )
        used_citation_keys.clear()  # リセット
        available_citations = citations
```

#### 改善3: バリデーション失敗の減少

**概要**:
- バリデーション失敗を減らすため、プロンプトを改善する
- または、バリデーション基準を緩和する

**適用箇所**: `backend/app/quiz/validator.py::validate_quiz_item()`

**例**:
```python
# バリデーション基準を緩和（一部の基準を削除または緩和）
# ただし、品質を維持するため、重要な基準は維持する
```

#### 改善4: 1回のLLM呼び出しで複数問生成

**概要**:
- `generate_and_validate_quizzes()`を改良し、1回のLLM呼び出しで複数問生成できるようにする

**適用箇所**: `backend/app/quiz/generator.py::generate_and_validate_quizzes()`

**例**:
```python
# count > 1 の場合も対応
# ただし、品質を維持するため、1回の呼び出しで生成する問数は制限する（例：最大3問）
if count > 3:
    logger.warning(f"count={count} が指定されましたが、1回の呼び出しで最大3問まで生成します")
    count = 3
```

#### 改善5: タイムアウト時間の調整

**概要**:
- タイムアウト時間を調整し、目標数に達するまで十分な時間を確保する

**適用箇所**: `backend/app/core/settings.py`

**例**:
```python
# タイムアウト時間を調整（デフォルト値の2倍）
max_total_time_sec = settings.ollama_timeout_sec * 2  # 現在の設定
# または、目標数に応じて動的に調整
max_total_time_sec = settings.ollama_timeout_sec * target_count
```

---

## 5. 再現手順と観測ポイント

### 5.1 問題1の再現手順

```bash
# 単一ソース指定でクイズ生成
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "source_ids": ["sample3.txt"],
    "save": true,
    "debug": true
  }' | jq '.quizzes[] | {statement: .statement, citations: .citations[].source}'
```

**観測ポイント**:
- `citations[].source`がすべて`sample3.txt`であることを確認
- `statement`に「火災」「避難」「災害」などのキーワードが含まれていないことを確認
- ログに「【重大】選択されたcitationのsourceが不一致」が出力されていないことを確認

### 5.2 問題2の再現手順

```bash
# 規定数（5問）を指定してクイズ生成
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "source_ids": ["sample3.txt"],
    "save": true,
    "debug": true
  }' | jq '{quizzes_count: (.quizzes | length), debug: .debug.generation}'
```

**観測ポイント**:
- `quizzes_count`が5であることを確認
- `debug.generation.accepted_count`が5であることを確認
- `debug.generation.attempts`が10以下であることを確認
- `debug.generation.elapsed_ms`が30000以下であることを確認

---

## 6. まとめ

### 6.1 問題1の根本原因

1. **Unicode正規化の不一致**: source_idsとpoolのキーの正規化が一致しない
2. **フィルタリングのタイミング**: chunk取得後にフィルタを適用している
3. **LLMの学習データ**: LLMが学習データから他のファイルの内容を想起する
4. **fallback_citationsの不整合**: statement生成前に取得したfallback_citationsが、statementと対応していない
5. **エラーハンドリングの不備**: source不一致を検出しても、スキップするだけでエラーを返さない

### 6.2 問題2の根本原因

1. **重複除外の多さ**: 重複が多すぎると、目標数に達する前に試行が終了する
2. **使用済みcitationsの不足**: 使用可能なcitationsが少なくなると、リセットしても目標数に達しない
3. **バリデーション失敗の多さ**: バリデーション失敗が多いと、目標数に達する前に試行が終了する
4. **1回のLLM呼び出しで1問のみ生成**: 効率が悪く、時間がかかる
5. **タイムアウト**: タイムアウトが発生すると、目標数に達する前に終了する

### 6.3 改善の優先順位

**問題1（ソース混入）**:
1. **最優先**: Unicode正規化の統一とエラーハンドリングの強化
2. **高**: フィルタリングのタイミングを早める
3. **中**: LLMプロンプトの改善
4. **中**: fallback_citationsの再検索
5. **低**: source不一致時のエラーハンドリングの強化

**問題2（規定数未達）**:
1. **最優先**: 重複判定の強化
2. **高**: 使用済みcitationsのリセットロジックの改善
3. **中**: バリデーション失敗の減少
4. **中**: 1回のLLM呼び出しで複数問生成
5. **低**: タイムアウト時間の調整

---

**調査者**: AI Assistant  
**最終更新**: 2026-01-23
