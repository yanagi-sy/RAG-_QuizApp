# 調査結果: 「クイズ0のcitationsが空配列、fallback_citationsを採用」の原因

## 結論

**C: LLMがcitationsを空で返し、コードがそれを信じてfallbackしている**

## 根拠

### 1. citationsが最終確定される箇所

**ファイル**: `backend/app/quiz/parser.py`  
**関数**: `_parse_single_quiz`  
**行**: 250-254

```python
# Citationをパース（LLMが返した場合）
if "citations" in quiz_data and isinstance(quiz_data["citations"], list):
    # 空配列チェック（LLMが [] を返した場合）
    if len(quiz_data["citations"]) == 0:
        logger.warning(f"クイズ {index} の citations が空配列、fallback_citations を採用")
        quiz_data["citations"] = fallback_citations[:3] if fallback_citations else []
```

### 2. データフロー

1. **retrieval**: `routers/quiz.py:90` → `retrieve_for_quiz()` でcitationsを取得
2. **選択**: `generation_handler.py:232` → 5件のcitationsから1件を選択 `[single_citation]`
3. **LLM呼び出し**: `generator.py:475` → `parse_quiz_json(response_text, citations, count)`
   - ここで `citations` が `fallback_citations` として渡される
4. **パース**: `parser.py:250` → LLMが返したJSONの `quiz_data["citations"]` をチェック
   - **問題**: LLMが `citations: []` を返している

### 3. プロンプトの指示

**ファイル**: `backend/app/llm/prompt.py:109`

```
- citations: 入力で渡された引用をそのまま使用
```

プロンプトには指示があるが、LLMが実際にcitationsを返しているかは未確認。

### 4. 原因の分類

- **A（retrieval自体が0件）**: ❌ 違う。retrievalは成功している（`citations=[single_citation]` が渡されている）
- **B（紐付け実装がない）**: ❌ 違う。プロンプトで「そのまま使用」と指示している
- **C（LLMが空で返す）**: ✅ **これが原因**。LLMがJSONで `citations: []` を返している

## 再現手順

```bash
curl -X POST http://localhost:8000/api/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{
    "level": "beginner",
    "count": 5,
    "source_ids": null,
    "save": false,
    "debug": true
  }'
```

## 追加ログ提案

以下の3箇所にログを追加して、LLMが返すJSONのcitationsを確認：

### 1. LLM生出力のcitations確認（`generator.py:475` 直前）

```python
# JSONパース（堅牢版、count件に制限）
t_parse_start = time.perf_counter()
logger.info(f"[PARSE:BEFORE] fallback_citations_count={len(citations)}, fallback_citations_preview={[f'{c.source}(p.{c.page})' for c in citations[:3]]}")
quizzes, parse_error, raw_excerpt = parse_quiz_json(response_text, citations, count)
```

### 2. LLMが返したJSONのcitations確認（`parser.py:250` 直前）

```python
# Citationをパース（LLMが返した場合）
logger.info(f"[PARSE:CITATIONS_CHECK] quiz_{index}_has_citations_key={'citations' in quiz_data}, quiz_{index}_citations_type={type(quiz_data.get('citations')).__name__ if 'citations' in quiz_data else 'N/A'}, quiz_{index}_citations_len={len(quiz_data.get('citations', [])) if isinstance(quiz_data.get('citations'), list) else 'N/A'}")
if "citations" in quiz_data and isinstance(quiz_data["citations"], list):
```

### 3. 選択されたcitationの確認（`generation_handler.py:246` 直後）

```python
for citation_idx, single_citation in enumerate(selected_citations_list):
    logger.info(f"[GENERATION:SELECTED_CITATION] citation_idx={citation_idx}, source={single_citation.source}, page={single_citation.page}, quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}")
    # 1つのcitationから正誤ペアを生成
```
