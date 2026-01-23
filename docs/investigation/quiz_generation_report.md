# クイズ生成品質調査レポート

## 1. 概要

本レポートは、rag-quiz-appのクイズ生成機能における以下の3つの主要課題について、現状コード・ログ・サンプル資料の根拠をもとに原因を特定し、改善方針と受入条件を明確化することを目的とする。

### 調査対象課題

1. **出題箇所の重複（悪い偏り）**: 同一論点の繰り返し、同一文の言い換え、肯定/否定の単純ペアで実質重複
2. **出題文の表現の不自然さ（客体ズレ等）**: 「出口を優先して避難誘導」のような客体ズレ、目的語ズレ、主語欠落、曖昧な指示語、冗長、規範表現の不整合、文末ゆれ等
3. **規定数（例：5問）が安定して揃わない**: 生成が遅い、attemptsが増加、目標数に達しない

### 調査方針

- 単一ソース指定は仕様として許容（テーマ範囲の限定はOK）
- ただし「同じ論点の繰り返し」「同一文の言い換え」「肯定/否定の単純ペアで実質重複」などの"悪い偏り"は改善対象
- 表現改善は「すべてのソース（PDF/テキスト）に対して一貫して自然な日本語を生成する仕組み」として設計
- 特定PDFの言い回しは「例」として参照し、改善方針は"全ソースに適用可能なルール/仕組み"としてまとめる

---

## 2. 現象の整理

### 2.1 観測ログ（代表例）

```
クイズ 0 の citations が空配列、fallback_citations を採用
出題箇所重複クイズを除外: '火災が発生した場合、店内では出口を優先して避難誘導を行わない。...' 
  (citations: ['防犯・災害対応マニュアル（サンプル）.pdf(p.5)', '防犯・災害対応マニュアル（サンプル）.pdf(p.4)'])
クイズ 0 の citations に dict 以外の要素: [{'index': 0, 'type': 'int', 'value': '1'}, {'index': 1, 'type': 'int', 'value': '4'}]、fallback_citations を採用
重複クイズを除外: '火災が発生した場合、店内では出口を優先して避難誘導を行う。...'
重複クイズを除外: '火災が発生した場合、店内では出口を優先して避難誘導を行わない。...'
[GENERATION_RETRY] attempt=2 でエラー: TypeError: can only concatenate str (not "int") to str
```

### 2.2 観測される問題パターン

#### 出題箇所の重複
- 同じcitationから○と×の両方が生成される
- 「行う/行わない」の単純反転が別問として混在
- 連続10回重複が発生し、無限ループ防止でスキップ

#### 表現の不自然さ
- 「店内では出口を優先して避難誘導を行う」→ 客体ズレ（「出口を優先」は不自然、「出口へ優先的に」が自然）
- 文脈（状況・条件・タイミング）が欠落している
- 根拠（citations.quote）とstatementの対応が崩れている可能性

#### 規定数未達・遅延
- count=5指定でも5問に達しない（attempts=10でも不足）
- 生成時間が長い（例：total=72s）
- rejected_itemsに`false_generation_failed`が並ぶ（mutator由来）

#### citations空・ソース逸脱
- 「クイズ 0 の citations が空配列、fallback_citations を採用」が繰り返し発生
- LLMが返すcitationsがdict以外（int, list, str）の形式
- 単一ソース指定時でも、fallbackで他ソースが混入する可能性

---

## 3. 関連モジュール一覧

### 3.1 処理フロー（入口→保存まで）

```
POST /quiz/generate
  ↓
backend/app/routers/quiz.py::generate_quizzes_endpoint()
  ↓
backend/app/quiz/retrieval.py::retrieve_for_quiz()
  - source_ids指定時のフィルタ
  - chunk_poolからサンプリング
  - chunk_selectorでlevel別フィルタ
  - citations作成（重複排除）
  ↓
backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()
  - 目標数に達するまで複数回試行
  - 重複チェック（statement、citation）
  - 使用済みcitationsの追跡
  ↓
backend/app/quiz/generator.py::generate_and_validate_quizzes()
  - LLM呼び出し（○のみ生成）
  - validatorチェック
  - mutatorで×生成
  ↓
backend/app/llm/prompt.py::build_quiz_generation_messages()
  - プロンプト構築（テンプレート指定、文脈指示）
  ↓
backend/app/llm/ollama.py::chat()
  - Ollama API呼び出し
  ↓
backend/app/quiz/parser.py::parse_quiz_json()
  - JSONパース
  - citations整形（fallback処理）
  ↓
backend/app/quiz/postprocess.py::postprocess_quiz_item()
  - statement正規化（【source】除去）
  - citations選別
  ↓
backend/app/quiz/validator.py::validate_quiz_item()
  - 形式チェック、曖昧表現チェック
  ↓
backend/app/quiz/mutator.py::make_false_statement()
  - ○から×を生成（単純否定/置換）
  ↓
backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()
  - 重複除外、バランス配置
  ↓
backend/app/quiz/store.py::save_quiz_set()
  - JSONファイル保存
```

### 3.2 関与ファイル一覧（パス付き）

| ファイル | 役割 | 主要関数/クラス |
|---------|------|---------------|
| `backend/app/routers/quiz.py` | APIエンドポイント | `generate_quizzes_endpoint()` |
| `backend/app/quiz/retrieval.py` | citationsサンプリング | `retrieve_for_quiz()` |
| `backend/app/quiz/chunk_pool.py` | chunk ID pool管理 | `get_pool()`, `sample_ids_multi_source()` |
| `backend/app/quiz/chunk_selector.py` | level別chunk選択 | `select_chunks()`, `score_chunk()` |
| `backend/app/quiz/generation_handler.py` | 再試行制御・重複除外 | `generate_quizzes_with_retry()`, `_is_duplicate()`, `_is_citation_duplicate()` |
| `backend/app/quiz/generator.py` | LLM生成・バリデーション | `generate_and_validate_quizzes()`, `generate_quizzes_with_llm()` |
| `backend/app/llm/prompt.py` | プロンプト構築 | `build_quiz_generation_messages()`, `build_quiz_json_fix_messages()` |
| `backend/app/quiz/parser.py` | JSONパース・citations整形 | `parse_quiz_json()`, `_parse_single_quiz()` |
| `backend/app/quiz/postprocess.py` | 後処理 | `postprocess_quiz_item()`, `_deduplicate_citations()` |
| `backend/app/quiz/validator.py` | バリデーション | `validate_quiz_item()` |
| `backend/app/quiz/mutator.py` | ○→×変換 | `make_false_statement()` |
| `backend/app/quiz/store.py` | 保存 | `save_quiz_set()` |
| `backend/app/core/settings.py` | 設定値 | `Settings` クラス |

---

## 4. 原因分析：重複（悪い偏り）

### 4.1 重複判定のキー

**現状実装** (`backend/app/quiz/generation_handler.py`):

```python
def _normalize_statement(statement: str) -> str:
    normalized = re.sub(r'\s+', '', statement)  # 空白除去
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')  # 句読点除去
    return normalized.lower()  # 小文字化

def _is_duplicate(new_statement: str, existing_statements: list[str]) -> bool:
    normalized_new = _normalize_statement(new_statement)
    for existing in existing_statements:
        normalized_existing = _normalize_statement(existing)
        if normalized_new == normalized_existing:
            return True
    return False
```

**問題点**:
- 正規化は「空白除去・句読点除去・小文字化」のみ
- **否定語（「行う/行わない」）の除去がない** → 「行う」と「行わない」が別物として扱われる
- 「火災が発生した場合、店内では出口を優先して避難誘導を行う」と「火災が発生した場合、店内では出口を優先して避難誘導を行わない」が重複として検出されない

**根拠**: ログに「重複クイズを除外: '...行う。...'」「重複クイズを除外: '...行わない。...'」が別々に出現していることから、正規化後の文字列が異なるため重複として検出されていない。

### 4.2 「行う/行わない」の単純反転が別問として混在する理由

**原因**:
1. `_normalize_statement()`が否定語を除去していない
2. ○と×は別々に処理され、それぞれが`accepted_statements`に追加される
3. 同じcitationから生成された○と×のペアが、citation重複チェックで除外される可能性があるが、statement重複チェックでは除外されない

**コード位置**: `backend/app/quiz/generation_handler.py:200-318`

```python
# ○を処理
for true_quiz in batch_true:
    if _is_duplicate(true_quiz.statement, accepted_statements):  # 否定語除去なし
        # 除外
    # ...

# ×を処理
for false_quiz in batch_false:
    if _is_duplicate(false_quiz.statement, accepted_statements):  # 否定語除去なし
        # 除外
    # ...
```

### 4.3 同一チャンク/同一セクションに集中する仕組み

**現状実装** (`backend/app/quiz/retrieval.py`):

- `sample_ids_multi_source()`でランダムサンプリング（均等分散）
- `chunk_selector.select_chunks()`でlevel別スコアリング（キーワードマッチ、見出しボーナス、長さボーナス）
- **セクション/見出し分散の制約がない** → 同一セクションから複数chunkが選ばれる可能性

**問題点**:
- スコアリングは「キーワード出現回数×重み」の合計のみ
- 同一セクション（同じ見出し下）から複数chunkが選ばれても、分散制約がない
- 結果として、同一論点が連続して出題される可能性

**根拠**: `chunk_selector.py`の`select_chunks()`はスコア降順で上位top_n件を返すのみ。セクション分散のロジックがない。

### 4.4 既出問題の「出力禁止（banned list）」の有無

**調査結果**: **存在しない**

- `build_quiz_generation_messages()`に既出statementを渡す仕組みがない
- retry時に「このstatementは既に生成済みなので避ける」という指示がない
- 結果として、LLMが同じstatementを繰り返し生成する可能性

**コード位置**: `backend/app/llm/prompt.py:66-292` - banned listの注入箇所なし

### 4.5 単一ソース指定時の制約

**現状実装** (`backend/app/quiz/retrieval.py:60-77`):

```python
# source_ids を NFC 正規化
if source_ids:
    source_ids = [unicodedata.normalize("NFC", s) for s in source_ids]
    sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
```

**問題点**:
- `sample_ids_multi_source()`は指定sourceからサンプルするが、**fallback時やcitations空時の処理で制約が緩和される可能性**
- `parser.py`でfallback_citationsを使用する際、source_ids制約が維持されているか不明

**根拠**: `parser.py:252-308`でfallback_citationsを使用する際、source_idsのフィルタリングがない。

---

## 5. 原因分析：表現（客体ズレ・不自然さ）

### 5.0 一般化の方針

「出口を優先して避難誘導」は一例にすぎない。表現品質課題を以下のカテゴリで整理する：

| カテゴリ | 例 | 原因候補 |
|---------|---|---------|
| **目的語ズレ** | 「出口を優先して」→「出口へ優先的に」 | 助詞の誤用、目的語の誤認識 |
| **主語欠落** | 「店内では...を行う」→「店舗スタッフは...を行う」 | 主語の省略、指示語の曖昧さ |
| **指示語の曖昧さ** | 「その場合」「この時」 | 指示語の多用、参照先不明確 |
| **助詞の不自然** | 「を優先して」→「へ優先的に」 | 助詞の誤用、語順の問題 |
| **二重否定** | 「してはならない」→「しない」 | 禁止表現の変換ミス |
| **語尾ゆれ** | 「する。」「します。」「である。」 | 文末の統一不足 |
| **冗長** | 「必ず行う必要がある」 | 重複表現 |
| **規範文体と断言文の不一致** | 「〜すること」「〜してはならない」→「〜する。」 | 文体変換の不完全 |

### 5.1 どこで不自然表現が生まれるか（発生源の特定）

#### 5.1.1 statementテンプレ/例文/システムプロンプト

**現状** (`backend/app/llm/prompt.py:117-145`):

```
T3: 「【状況・条件】の場合、【対象】では【行為】を必ず行う。」
  例: 「火災が発生した場合、店内では出口を優先して避難誘導を行う。」
```

**問題点**:
- **例文に「出口を優先して」という不自然表現が含まれている**
- この例がLLMに「客体ズレ」を学習させている可能性
- テンプレート自体は「【行為】を必ず行う」とシンプルだが、例文が不自然

**根拠**: プロンプト内に「出口を優先して避難誘導」という例が複数箇所（123, 129, 133, 139, 141, 143, 145, 174, 175, 270, 271行目）に出現。

#### 5.1.2 LLMへの入力（引用文/要約/キーワード）

**現状** (`backend/app/llm/prompt.py:193-221`):

- citationsのquoteをそのままLLMに渡す
- quoteは最大200文字にトリム（`settings.quiz_quote_max_len`）
- 引用が断片的（見出しだけ/箇条書きだけ）の場合、断言文に変換する際に目的語が崩れる可能性

**問題点**:
- 引用が「出口へ誘導する」と書かれていても、LLMが「出口を優先して誘導する」と誤変換する可能性
- 引用の文脈（前後の文）が欠落しているため、目的語や主語が不明確になる

**根拠**: `retrieval.py:136-138`でquoteを`text[:max_len]`で切り詰めている。前後の文脈が失われる。

#### 5.1.3 mutator（false生成）が表現を壊しているか

**現状** (`backend/app/quiz/mutator.py:91-187`):

- 単純な文字列置換（「行う」→「行わない」など）
- 正規表現置換（数値の反転など）
- 文末の否定化（「する。」→「しない。」など）

**問題点**:
- **助詞や目的語を考慮しない単純置換** → 「出口を優先して行う」→「出口を優先して行わない」となり、助詞「を」が不自然なまま残る
- 文脈を考慮しないため、「出口へ優先的に誘導する」のような自然な表現に変換できない

**根拠**: `mutator.py:122-126`で`statement.replace(pattern, replacement, 1)`という単純置換のみ。構文解析や助詞の調整がない。

#### 5.1.4 生成後の後処理（整形/正規化/言い換え補正）

**現状** (`backend/app/quiz/postprocess.py:16-59`):

- `【source】`等のメタ情報除去
- citationsの重複排除
- **表現の正規化や言い換え補正はない**

**問題点**:
- 客体ズレ、助詞の不自然さ、主語欠落などを検知・修正する処理がない
- 後処理は「メタ情報除去」と「citations選別」のみ

**根拠**: `postprocess.py`のコードを確認。表現品質のチェックや修正処理がない。

### 5.2 根拠とstatementの対応（ソース非依存に担保できているか）

**現状実装** (`backend/app/quiz/parser.py:249-308`):

- LLMが返すcitationsをそのまま使用
- citationsが空/不正形式の場合、fallback_citationsを使用
- **statementとcitations.quoteの対応関係を検証する処理がない**

**問題点**:
- 根拠（citations.quote）に「出口へ誘導」と書かれていても、statementが「出口を優先して誘導」になっている可能性
- LLMが引用を「創作」している可能性（引用に無い語をstatementに追加）

**根拠**: `parser.py`ではcitationsの形式チェックのみ。statementとquoteの語彙対応チェックがない。

**citations空→fallback採用の際**:

- `parser.py:252-254`でfallback_citationsを使用
- **statementに合わせて再検索して根拠を付け直す設計がない**
- fallback_citationsはretrieval時に取得したもの（statement生成前）なので、statementと対応していない可能性

### 5.3 表現品質を"全ソース共通"で改善する改善案の方向性

#### (A) プロンプトでの制約強化（優先度: 高）

**概要**:
- 断言文の型を明確化（「【対象】は【目的語】に【行為】する」形式）
- 助詞の自然さを指示（「を」→「へ」「に」の使い分け）
- 目的語の明確化を必須化
- 曖昧語禁止（「その」「この」など）
- 文末統一（「する。」のみ）

**適用箇所**: `backend/app/llm/prompt.py::build_quiz_generation_messages()`

**例**:
```
statementテンプレート:
- 「【状況】の場合、【主体】は【目的語】に【行為】する。」
- 「【状況】の場合、【主体】は【目的語】へ【行為】する。」
- 助詞ルール: 移動・方向は「へ」、対象は「を」、場所は「で」
```

#### (B) validatorでの品質検知（優先度: 高）

**概要**:
- 客体ズレ検知: 「を優先して」→「へ優先的に」のパターンチェック
- 主語欠落検知: 「店内では」→「店舗スタッフは」の明確化チェック
- 曖昧語検知: 「その」「この」「それ」などの指示語チェック
- 不自然助詞検知: 「を優先して」「に確認する」などのパターンチェック
- 検知された場合は再生成対象

**適用箇所**: `backend/app/quiz/validator.py::validate_quiz_item()`

**例**:
```python
UNNATURAL_PATTERNS = [
    (r"を優先して", "客体ズレ: 'を優先して'は不自然。'へ優先的に'または'を優先的に'を使用"),
    (r"その\w+", "曖昧指示語: 'その'は参照先が不明確"),
    # ...
]
```

#### (C) 後処理の正規化（優先度: 中）

**概要**:
- 句点/空白/語尾/表記ゆれ統一
- 過度に抽象的な目的語の補正（一般ルールとして）
- ただし、全ソース共通のルールに限定（特定ソース依存は避ける）

**適用箇所**: `backend/app/quiz/postprocess.py::postprocess_quiz_item()`

**例**:
```python
# 助詞の統一（全ソース共通）
statement = re.sub(r"を優先して", "へ優先的に", statement)
# ただし、文脈を考慮しない単純置換は危険（要改善）
```

#### (D) 根拠整合（優先度: 中）

**概要**:
- statementで再検索し根拠を再付与
- または根拠語彙をstatementに"必ず含める"制約
- 単一ソース制約を維持

**適用箇所**: `backend/app/quiz/generator.py` または新規モジュール

**例**:
```python
# statement生成後、statementのキーワードで再検索
# 根拠を再付与（単一ソース制約を維持）
```

#### (E) mutator改良（優先度: 低）

**概要**:
- 単純否定ではなく、条件/主体/手順/例外の誤りに変える
- 表現破綻を減らす（助詞を考慮した変換）

**適用箇所**: `backend/app/quiz/mutator.py::make_false_statement()`

**例**:
```python
# 「行う」→「行わない」ではなく
# 「【条件A】の場合に行う」→「【条件B】の場合に行う」に変更
```

### 5.4 テンプレ例の提示（全ソース共通の型）

**現状の問題**: プロンプトの例文に「出口を優先して」という不自然表現が含まれている。

**改善案**: 全ソースに適用できる断言文テンプレ（型）を提案

#### 型1: 状況・主体・行為
```
「【状況】の場合、【主体】は【行為】する。」
例: 「火災が発生した場合、店舗スタッフは避難誘導を行う。」
```

#### 型2: 状況・主体・目的語・行為
```
「【状況】の場合、【主体】は【目的語】に【行為】する。」
例: 「緊急時において、店舗スタッフは出口へ避難誘導を行う。」
```

#### 型3: 状況・主体・目的語・方法・行為
```
「【状況】の場合、【主体】は【目的語】を【方法】で【行為】する。」
例: 「高齢者がいる場合、店舗スタッフは出口を優先的に避難誘導する。」
```

**注意**: 「出口を優先して」ではなく「出口を優先的に」または「出口へ優先的に」が自然。

---

## 6. 原因分析：規定数未達・遅延

### 6.1 LLMが1回でcount問を返せないケースの存在とハンドリング

**現状実装** (`backend/app/quiz/generator.py:56-92`):

- `generate_and_validate_quizzes()`は`count=1`専用
- `generation_handler.py`で1問ずつループ生成
- 各試行で○と×の2件を生成（最大2件）

**問題点**:
- 1回のLLM呼び出しで1問（○1件）のみ生成
- ×はmutatorで生成（LLMが返すfalse_statementがあれば使用）
- 目標5問に達するには、最低3回の試行が必要（○3件+×2件、または○2件+×3件）
- 重複やvalidator落ちが多いと、attemptsが増加

**根拠**: `generation_handler.py:180-188`で`count=1`で呼び出し。`generator.py:89-92`で`count > 1`の場合は1に制限。

### 6.2 attempts増加の原因（理由別集計）

**現状ログから推測される原因**:

1. **重複除外** (`generation_handler.py:203-209, 247-253`):
   - statement重複: `_is_duplicate()`で検出
   - citation重複: `_is_citation_duplicate()`で検出
   - ログ: 「重複クイズを除外」「出題箇所重複クイズを除外」

2. **validator落ち** (`generator.py:190, 280`):
   - 曖昧表現、疑問形、短すぎ、citations空など
   - ログ: `rejected_items`に`reason`が記録される

3. **false生成失敗** (`generator.py:314-323`):
   - mutatorが失敗（元の文と同じを返す）
   - ログ: `reason: "false_generation_failed"`

4. **LLM否定文reject** (`generator.py:179-187`):
   - LLMが勝手に×を作るのを防ぐ
   - ログ: `reason: "llm_negative_phrase"`

5. **TypeError** (`generator.py:214`):
   - ログ出力で文字列と整数の連結エラー
   - 処理は続行されるが、ログが乱れる

**根拠**: ログに「重複クイズを除外」「出題箇所重複クイズを除外」「[GENERATION_RETRY] attempt=X でエラー」が繰り返し出現。

### 6.3 false_generation_failed の発生箇所と条件

**発生箇所** (`backend/app/quiz/generator.py:314-323`):

```python
if false_statement and false_statement != original_statement:
    # ×をvalidatorでチェック
    # ...
else:
    # false_statementが取得できなかった or 元と同じ
    logger.warning(f"False statementの生成に失敗 (source={false_source})")
    rejected.append({
        "statement": original_statement[:100],
        "reason": "false_generation_failed",
        "false_source": false_source,
    })
```

**発生条件**:
1. LLMがfalse_statementを返さない
2. mutatorが失敗（元の文と同じを返す）
3. mutatorの代替方法も失敗

**mutator失敗パターン** (`backend/app/quiz/mutator.py:136-187`):
- どのルールにも該当しない
- 最終手段（文末否定化）も該当しない
- 「必ず」「必須」「必要」の削除/置換も失敗

**根拠**: ログに`false_generation_failed`が並ぶ。`mutator.py:137`で「Mutator失敗: 変換ルールが見つかりませんでした」が出力される。

### 6.4 "出力禁止（banned）"や"多様性制約"の有無

**調査結果**: **存在しない**

- `build_quiz_generation_messages()`に既出statementを渡す仕組みがない
- retry時に「このstatementは既に生成済みなので避ける」という指示がない
- 結果として、LLMが同じstatementを繰り返し生成する可能性

**根拠**: `prompt.py`のコードを確認。banned listの注入箇所がない。

### 6.5 debugログの指標

**現状** (`backend/app/quiz/debug_builder.py:53-133`):

- `accepted_count`: 採用されたクイズ数
- `rejected_count`: バリデーション失敗数
- `attempts`: 試行回数
- `elapsed_ms`: 処理時間
- `dropped_reasons`: 理由別の集計
- `final_true_count`, `final_false_count`: ○と×の最終数

**不足している指標**:
- 重複除外数（statement重複、citation重複を分けて）
- false生成成功率（mutator成功/失敗の割合）
- banned適用状況（現状は未実装）
- 表現品質の落下理由（客体ズレ、主語欠落など）

---

## 7. 原因分析：citations空・ソース逸脱

### 7.1 citations をどこで付けているか

**現状実装**:

1. **LLMが返す** (`parser.py:250-304`):
   - LLMがJSONの`citations`フィールドに含める
   - 形式チェック: dictかどうか、source/quoteが空でないか
   - 不正形式の場合はfallbackを使用

2. **後付け（fallback）** (`parser.py:252-254, 271, 304, 308`):
   - citationsが空/不正形式の場合、`fallback_citations`を使用
   - `fallback_citations`は`retrieve_for_quiz()`で取得したもの

**問題点**:
- LLMが返すcitationsが不正形式（int, list, str）の場合、fallbackを使用
- fallback_citationsはstatement生成前のものなので、statementと対応していない可能性

**根拠**: ログに「クイズ 0 の citations に dict 以外の要素: [{'index': 0, 'type': 'int', 'value': '1'}]」が出現。

### 7.2 citationsが空のとき、fallback_citations はどこから取るか

**現状実装** (`backend/app/quiz/generator.py:118-129`):

```python
# generate_and_validate_quizzes()にcitationsを渡す
batch_accepted, batch_rejected, batch_attempt_errors, batch_stats = await generate_and_validate_quizzes(
    level=request.level,
    count=1,
    topic=request.topic,
    citations=selected_citations,  # 選択したcitationsを使用
    request_id=request_id,
    attempt_index=attempts,
)
```

**fallback_citationsの流れ**:
1. `generation_handler.py:185`で`selected_citations`を選択（使用済みを除外）
2. `generator.py:60`で`citations`として受け取る
3. `generator.py:122`で`generate_quizzes_with_llm()`に渡す
4. `generator.py:129`で`parse_quiz_json()`に`fallback_citations=citations`として渡す
5. `parser.py:17`で`fallback_citations`として受け取る

**問題点**:
- `selected_citations`は使用済みを除外したものだが、**statement生成後に再検索していない**
- fallback_citationsはstatementと対応していない可能性

### 7.3 sources指定（例:"防犯・安全ナレッジベース.pdf"）が metadata.source と一致しているか

**現状実装** (`backend/app/quiz/retrieval.py:60-77`):

```python
# source_ids を NFC 正規化
if source_ids:
    source_ids = [unicodedata.normalize("NFC", s) for s in source_ids]
    sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
```

**chunk_pool.py** (`backend/app/quiz/chunk_pool.py:74-84`):

```python
for chunk_id, metadata in zip(ids, metadatas):
    source_raw = metadata.get("source", "unknown")
    source_norm = unicodedata.normalize("NFC", source_raw)  # NFC正規化
    pool[source_norm].append(chunk_id)
```

**問題点**:
- source_idsとmetadata.sourceの両方をNFC正規化しているが、**厳密一致で0件になる可能性**
- ファイル名の表記ゆれ（拡張子の有無、スペース、全角/半角）で一致しない可能性

**根拠**: `retrieval.py:229-230`で`pool_sources = [s for s in source_ids if s in pool]`としているが、一致しない場合は空リストになる。

### 7.4 statementと根拠の対応を担保する仕組みがあるか

**調査結果**: **存在しない**

- statement生成後に、statementのキーワードで再検索して根拠を付け直す設計がない
- fallback_citationsはstatement生成前のものなので、対応関係が崩れる可能性

**根拠**: `generator.py`と`parser.py`のコードを確認。statementで再検索する処理がない。

---

## 8. 再現手順と観測ポイント

### 8.1 curlでの再現手順

#### 単一ソース指定
```bash
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "source_ids": ["防犯・災害対応マニュアル（サンプル）.pdf"],
    "save": true,
    "debug": true
  }' | jq '.quizzes | length, .quizzes[].statement, .debug.stats'
```

#### ソース未指定（全資料対象）
```bash
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "save": true,
    "debug": true
  }' | jq '.quizzes | length, .quizzes[].statement, .debug.stats'
```

### 8.2 debug出力で見るべき項目と期待値

**現状のdebug項目** (`backend/app/quiz/debug_builder.py`):

```json
{
  "request": {
    "level": "beginner",
    "count": 5,
    "target_count": 5,
    "source_ids": ["防犯・災害対応マニュアル（サンプル）.pdf"]
  },
  "retrieval": {
    "citations_count": 10,
    "elapsed_ms": 123.4,
    "quiz_pool_sources": [...],
    "quiz_sources_unique": [...]
  },
  "generation": {
    "accepted_count": 3,  // 期待値: 5
    "target_count": 5,
    "rejected_count": 15,
    "attempts": 8,  // 期待値: 3-5
    "elapsed_ms": 45000.0  // 期待値: 20000以下
  },
  "stats": {
    "generated_true_count": 5,
    "generated_false_count": 3,
    "dropped_reasons": {
      "duplicate_statement": 5,
      "duplicate_citation": 8,
      "false_generation_failed": 2
    },
    "final_true_count": 3,
    "final_false_count": 2
  }
}
```

**期待値**:
- `accepted_count` = `target_count` (5問)
- `attempts` ≤ 5回
- `elapsed_ms` ≤ 30000ms
- `dropped_reasons.duplicate_statement` ≤ 2
- `dropped_reasons.duplicate_citation` ≤ 3
- `dropped_reasons.false_generation_failed` = 0

### 8.3 追加すべきログ（提案）

1. **重複除外の詳細**:
   - statement重複数、citation重複数を分けて記録
   - 重複したstatementのプレビュー（最初の50文字）

2. **false生成の成功率**:
   - mutator成功数、失敗数、失敗理由

3. **表現品質の落下理由**:
   - 客体ズレ、主語欠落、曖昧語などの検知数

4. **sourcesフィルタ後のdoc数**:
   - source_ids指定時、フィルタ後のchunk数
   - 一致しなかったsource_idsのリスト

5. **banned適用状況**:
   - banned listの件数、適用されたかどうか（現状は未実装）

6. **citations空の詳細**:
   - LLMが返したcitationsの形式（dict/int/list/str）
   - fallback使用回数

---

## 9. 改善案（優先度順、概要のみ）

### 優先度: 高

#### 1. 重複判定キーを"コア内容キー"に強化

**概要**:
- `_normalize_statement()`に否定語除去を追加
- 「行う/行わない」「する/しない」などの否定語を除去してから比較
- コア内容（状況・主体・目的語・行為）のみで重複判定

**適用箇所**: `backend/app/quiz/generation_handler.py::_normalize_statement()`

**例**:
```python
def _normalize_statement(statement: str) -> str:
    # 否定語除去
    normalized = re.sub(r'しない|行わない|ではない|なくてもよい', '', statement)
    # 既存の正規化処理
    normalized = re.sub(r'\s+', '', normalized)
    # ...
    return normalized.lower()
```

#### 2. retry時に既出/重複落ちstatementをbanned listとしてプロンプトへ注入

**概要**:
- `accepted_statements`と`all_rejected_items`（重複理由）をbanned listとして構築
- `build_quiz_generation_messages()`にbanned listを渡す
- プロンプトに「以下のstatementは既に生成済みなので避ける」という指示を追加

**適用箇所**: 
- `backend/app/quiz/generation_handler.py::generate_quizzes_with_retry()`
- `backend/app/llm/prompt.py::build_quiz_generation_messages()`

**例**:
```python
# generation_handler.py
banned_statements = accepted_statements + [item["statement"] for item in all_rejected_items if item.get("reason") == "duplicate_statement"]

# prompt.py
if banned_statements:
    user_content += f"\n\n【出力禁止】以下のstatementは既に生成済みなので避ける:\n" + "\n".join(f"- {s[:50]}..." for s in banned_statements[:10])
```

#### 3. validatorに"表現品質チェック"を追加し、不自然文は再生成対象にする

**概要**:
- 客体ズレ、主語欠落、曖昧語、不自然助詞などを簡易ルールで検知
- 検知された場合は`reason`を返し、再生成対象にする

**適用箇所**: `backend/app/quiz/validator.py::validate_quiz_item()`

**例**:
```python
UNNATURAL_PATTERNS = [
    (r"を優先して", "object_shift: 'を優先して'は不自然。'へ優先的に'または'を優先的に'を使用"),
    (r"その\w+", "ambiguous_reference: 'その'は参照先が不明確"),
    (r"店内では\w+を行う", "missing_subject: 主語が不明確。'店舗スタッフは'などを明示"),
]

for pattern, reason in UNNATURAL_PATTERNS:
    if re.search(pattern, statement):
        return (False, reason)
```

#### 4. statement生成テンプレ/例文を「全ソース共通の型」に寄せる（客体ズレを防ぐ）

**概要**:
- プロンプトの例文から「出口を優先して」という不自然表現を削除
- 全ソース共通の自然な例文に置き換え
- 助詞の使い分けルールを明示

**適用箇所**: `backend/app/llm/prompt.py::build_quiz_generation_messages()`

**例**:
```
❌ 削除: 「火災が発生した場合、店内では出口を優先して避難誘導を行う。」
✅ 追加: 「火災が発生した場合、店舗スタッフは出口へ避難誘導を行う。」
```

### 優先度: 中

#### 5. チャンク選択に多様性制約（見出し/セクション分散）を導入

**概要**:
- 同一見出し/セクションから複数chunkが選ばれないように制約
- 見出しパターンでセクションを識別し、分散を確保

**適用箇所**: `backend/app/quiz/chunk_selector.py::select_chunks()`

**例**:
```python
# 見出しでセクションを識別
section_key = extract_section(text)  # 見出しパターンから抽出
# 同一セクションからは最大1件まで
```

#### 6. citations空の場合、statementで再検索し根拠を再付与（単一ソース制約を維持）

**概要**:
- statement生成後、statementのキーワードで再検索
- 根拠を再付与（単一ソース制約を維持）
- fallback_citationsではなく、statementに合わせた根拠を使用

**適用箇所**: 新規モジュール `backend/app/quiz/citation_matcher.py` または `generator.py`内

**例**:
```python
# statement生成後
if not quiz.citations or len(quiz.citations) == 0:
    # statementのキーワードで再検索（source_ids制約を維持）
    matched_citations = search_citations_for_statement(quiz.statement, source_ids)
    quiz.citations = matched_citations
```

#### 7. false問題の作り方を「単純否定」依存から、誤条件/誤手順/誤タイミング等へ段階的に改善

**概要**:
- mutatorを改良し、単純否定ではなく誤条件/誤手順/誤タイミングに変更
- より自然な×問題を生成

**適用箇所**: `backend/app/quiz/mutator.py::make_false_statement()`

**例**:
```python
# 「行う」→「行わない」ではなく
# 「【条件A】の場合に行う」→「【条件B】の場合に行う」に変更
# または「【手順1】→【手順2】」→「【手順2】→【手順1】」に変更
```

### 優先度: 低

#### 8. 後処理の正規化（全ソース共通ルール）

**概要**:
- 句点/空白/語尾/表記ゆれ統一
- ただし、全ソース共通のルールに限定

**適用箇所**: `backend/app/quiz/postprocess.py::postprocess_quiz_item()`

---

## 10. 受入条件（具体的チェック項目）

以下を満たしたら改善完了とする。

### 10.1 規定数の達成率

- **条件**: `count=5`指定で、**95%以上**で5問揃う
- **測定**: 100回生成して、5問揃った回数が95回以上
- **attempts上限**: 平均attempts ≤ 5回、最大attempts ≤ 8回

### 10.2 重複の排除

- **条件**: 同一コア内容（行う/行わない等）の問題が同一セット内に**2問以上入らない**
- **測定**: 生成されたクイズセット内で、`_normalize_statement()`（否定語除去後）で重複チェック
- **重複率**: 重複クイズ数 / 総生成数 ≤ 5%

### 10.3 表現の自然さ

- **条件**: statementの表現が自然（客体ズレ・曖昧指示語などが一定基準で検知されない）
- **測定**: validatorの表現品質チェックで検知されない
- **検知率**: 表現品質エラー数 / 総生成数 ≤ 10%

### 10.4 根拠との対応

- **条件**: statementとcitations.quoteが対応する（statementの語彙がquoteに含まれる、またはstatementで再検索した根拠を使用）
- **測定**: statementの主要語彙（動詞、目的語）がcitations.quoteに含まれる割合 ≥ 80%

### 10.5 citations空の解消

- **条件**: citationsが空のquizが出ない、または必ず同一ソース制約で補完される
- **測定**: `citations`が空のquiz数 = 0
- **fallback使用率**: fallback_citations使用数 / 総生成数 ≤ 20%

### 10.6 単一ソース制約の維持

- **条件**: 単一ソース指定時、citations.sourceが指定ソース以外を含まない（混入ゼロ）
- **測定**: `source_ids=["A.pdf"]`指定時、`citations[].source`がすべて`"A.pdf"`（NFC正規化後）
- **混入率**: 0%

### 10.7 生成速度

- **条件**: 5問生成の平均時間 ≤ 30秒
- **測定**: `debug.total.elapsed_ms`の平均 ≤ 30000ms

---

## 11. 追加で確認すべき点（不明点/ログ追加提案）

### 11.1 不明点

1. **LLMが返すcitationsがint/list形式になる原因**:
   - 推測: LLMのJSONパースエラー、またはLLMが誤った形式で返している
   - 確認方法: LLM生出力（`llm_output_preview_head`）をログに出力し、citationsフィールドの形式を確認

2. **source_idsとmetadata.sourceの一致率**:
   - 推測: ファイル名の表記ゆれで一致しない可能性
   - 確認方法: `retrieval.py`に「一致しなかったsource_ids」をログ出力

3. **「出口を優先して」という表現がLLMに学習されている可能性**:
   - 推測: プロンプトの例文が原因
   - 確認方法: プロンプトの例文を変更して再生成し、表現が改善されるか確認

### 11.2 ログ追加提案

1. **重複除外の詳細**:
   ```python
   logger.info(f"[DUPLICATE] statement重複: {count_statement}, citation重複: {count_citation}")
   ```

2. **false生成の成功率**:
   ```python
   logger.info(f"[MUTATOR] 成功: {success_count}, 失敗: {fail_count}, 失敗理由: {fail_reasons}")
   ```

3. **表現品質の検知**:
   ```python
   logger.warning(f"[QUALITY] 客体ズレ検知: {statement[:50]}... (reason: {reason})")
   ```

4. **sourcesフィルタ結果**:
   ```python
   logger.info(f"[RETRIEVAL] source_ids指定: {source_ids}, 一致したsources: {matched_sources}, 一致しなかったsources: {unmatched_sources}")
   ```

5. **banned適用状況**:
   ```python
   logger.info(f"[BANNED] banned_statements数: {len(banned_statements)}, プロンプトに注入: {injected}")
   ```

---

## 12. まとめ

### 12.1 主要な原因

1. **出題箇所の重複**: 
   - 重複判定キーが弱い（否定語除去なし）
   - banned listがない（LLMが同じstatementを繰り返し生成）
   - セクション分散制約がない（同一論点が連続）

2. **表現の不自然さ**:
   - プロンプトの例文に不自然表現が含まれている
   - validatorに表現品質チェックがない
   - 後処理で表現の正規化がない

3. **規定数未達・遅延**:
   - 重複除外が多い（attempts増加）
   - false生成失敗が多い（mutatorの変換ルール不足）
   - 1回のLLM呼び出しで1問のみ生成（効率が悪い）

4. **citations空・ソース逸脱**:
   - LLMが返すcitationsが不正形式
   - statementと根拠の対応関係を検証する処理がない
   - fallback_citationsがstatementと対応していない

### 12.2 改善の優先順位

1. **最優先**: 重複判定キーの強化、banned listの導入、validatorに表現品質チェック
2. **高**: プロンプトの例文修正、statementで再検索して根拠を再付与
3. **中**: セクション分散制約、mutator改良
4. **低**: 後処理の正規化

### 12.3 次のステップ

1. 改善案の実装（優先度順）
2. 受入条件のテスト実施
3. ログ追加と観測
4. 継続的な品質監視

---

**調査日**: 2026-01-22  
**調査者**: AI Assistant  
**対象バージョン**: 最新のmasterブランチ
