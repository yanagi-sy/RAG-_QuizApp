"""
クイズのJSONパース
"""
import json
import logging
import uuid

from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation

# ロガー設定
logger = logging.getLogger(__name__)


def parse_quiz_json(
    response_text: str,
    fallback_citations: list[Citation],
    count: int = 1,
) -> tuple[list[QuizItemSchema], str | None, str]:
    """
    LLMレスポンスからクイズをパース（○×問題専用、堅牢化版）
    
    - 空応答チェック
    - コードフェンス優先抽出
    - 先頭/末尾の余計な文字除去
    - JSON形式のパース（best effort）
    - statement フィールドの確認（question も互換性のため許容）
    - UUIDの生成
    - count件に制限（LLMが余分に返しても先頭count件のみ処理）
    
    Args:
        response_text: LLMからのレスポンステキスト
        fallback_citations: パースに失敗した場合のフォールバック引用
        count: 処理するクイズの最大数（デフォルト: 1）
        
    Returns:
        (items, parse_error, raw_excerpt) のタプル
        - items: パースされたクイズのリスト
        - parse_error: パースエラー文字列（成功時はNone）
        - raw_excerpt: レスポンステキストの先頭200文字（debug用）
    """
    # raw_excerpt を保存（debug用）
    raw_excerpt = response_text[:200] if response_text else ""
    
    # [観測ログB] LLM生出力のプレビュー
    logger.info(
        f"[PARSE:RAW_PREVIEW] "
        f"raw_len={len(response_text) if response_text else 0}, "
        f"raw_head={response_text[:150] if response_text else 'EMPTY'}"
    )
    
    # JSONブロックを抽出（堅牢版）
    response_text = response_text.strip()
    try:
        response_text = _extract_json_block_robust(response_text)
    except ValueError as e:
        # 空応答の場合
        if "empty_response" in str(e):
            return ([], "empty_response", raw_excerpt)
        return ([], f"json_extraction_error: {str(e)}", raw_excerpt)
    
    # JSONパース
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {e}")
        logger.error(f"レスポンステキスト（先頭500文字）: {response_text[:500]}")
        return ([], f"json_parse_error: {str(e)}", raw_excerpt)
    
    # quizzesキーの確認
    if "quizzes" not in data:
        return ([], "json_validation_error: JSONに 'quizzes' キーが含まれていません", raw_excerpt)
    
    quizzes_data = data["quizzes"]
    if not isinstance(quizzes_data, list):
        return ([], "json_validation_error: 'quizzes' はリストである必要があります", raw_excerpt)
    
    # LLMが余分に返した場合、先頭count件に制限（機械的truncate）
    original_count = len(quizzes_data)
    if len(quizzes_data) > count:
        logger.info(f"[PARSE:TRUNCATE] LLMが{original_count}件返したため、先頭{count}件に制限")
        quizzes_data = quizzes_data[:count]
    
    # [観測ログB] JSONのキーと各quizの型
    logger.info(
        f"[PARSE:JSON_KEYS] "
        f"data_keys={list(data.keys())}, "
        f"quizzes_count={len(quizzes_data)} (original={original_count})"
    )
    
    # 各quizの型を確認
    quiz_types = [type(q).__name__ for q in quizzes_data]
    logger.info(
        f"[PARSE:QUIZ_ITEM_TYPES] "
        f"types={quiz_types}"
    )
    
    # 各クイズをパース
    quizzes = []
    for i, quiz_data in enumerate(quizzes_data):
        try:
            # 救済: quiz_data が str の場合に dict へ変換
            if isinstance(quiz_data, str):
                logger.warning(f"クイズ {i} が str 形式のため dict に救済変換: {quiz_data[:50]}")
                
                # 文字列をstatementとして扱い、dictに変換
                statement = quiz_data.strip()
                
                # 末尾が断言形になるよう不足なら「。」を付ける
                if statement and not statement.endswith(("。", ".", "！", "!", "？", "?")):
                    statement += "。"
                
                quiz_data = {
                    "type": "true_false",
                    "statement": statement,
                    "answer_bool": True,  # ○のみ方針
                    "explanation": "引用に基づく正しい断言文です。",
                    # citations は fallback_citations の先頭3件を付与
                    "citations": [
                        {
                            "source": c.source,
                            "page": c.page,
                            "quote": c.quote,
                        }
                        for c in fallback_citations[:3]
                    ] if fallback_citations else []
                }
            
            quiz_item = _parse_single_quiz(quiz_data, i, fallback_citations)
            if quiz_item:
                quizzes.append(quiz_item)
        except Exception as e:
            logger.warning(f"クイズ {i} のパースに失敗: {e}")
            continue
    
    # 成功
    return (quizzes, None, raw_excerpt)


def _extract_json_block_robust(text: str) -> str:
    """
    マークダウンのJSONブロックを抽出（堅牢版）
    
    処理順序（優先度順）:
    1. 空応答チェック
    2. コードフェンス（```json ... ``` / ``` ... ```）を優先的に抽出
    3. 先頭/末尾の余計な文字（"Here is ...", "以下は..." など）を除去
    4. 最初の { から最後の } を抽出
    
    Args:
        text: レスポンステキスト
        
    Returns:
        JSONテキスト
        
    Raises:
        ValueError: 空応答または抽出失敗の場合
    """
    # 空応答チェック（空白のみも含む）
    if not text or not text.strip():
        raise ValueError("empty_response")
    
    original_text = text
    text = text.strip()
    
    # Step 1: コードフェンス（```json ... ``` / ``` ... ```）を優先的に剥がす
    # ```json で始まる場合
    if "```json" in text:
        start_idx = text.find("```json")
        text = text[start_idx + 7:]  # "```json" を削除
        # 対応する ``` を探す
        end_idx = text.find("```")
        if end_idx >= 0:
            text = text[:end_idx]
        text = text.strip()
        logger.info("コードフェンス（```json）を除去")
    # ``` で始まる場合（json なし）
    elif "```" in text:
        start_idx = text.find("```")
        text = text[start_idx + 3:]  # "```" を削除
        # 対応する ``` を探す
        end_idx = text.find("```")
        if end_idx >= 0:
            text = text[:end_idx]
        text = text.strip()
        logger.info("コードフェンス（```）を除去")
    
    # Step 2: 先頭の余計な文字を除去（"Here is", "以下は", "これが" など）
    # 改行より前の部分が短い（50文字以内）で { を含まない場合は削除
    lines = text.split("\n", 1)
    if len(lines) > 1 and len(lines[0]) < 50 and "{" not in lines[0]:
        text = lines[1].strip()
        logger.info(f"先頭の余計な文字を除去: {lines[0][:30]}")
    
    # Step 3: 最初の { から最後の } を抽出
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace >= 0 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
        logger.info(f"JSONブロック抽出成功: {len(text)}文字")
    else:
        # { } が見つからない場合はエラー
        logger.error(f"JSONブロックの {{}} が見つかりません（先頭200文字）: {original_text[:200]}")
        raise ValueError("json_extraction_error: {} が見つかりません")
    
    return text


def _parse_single_quiz(
    quiz_data: dict,
    index: int,
    fallback_citations: list[Citation]
) -> QuizItemSchema | None:
    """
    単一のクイズデータをパース
    
    Args:
        quiz_data: クイズデータ（dict）
        index: クイズのインデックス
        fallback_citations: フォールバック引用
        
    Returns:
        QuizItemSchema または None（パース失敗時）
    """
    # IDを生成（LLMが返さない場合）
    if "id" not in quiz_data or not quiz_data["id"]:
        quiz_data["id"] = str(uuid.uuid4())[:8]  # 短いID
    
    # statement フィールドの確認（question も互換性のため許容）
    if "statement" not in quiz_data:
        if "question" in quiz_data:
            # 互換性のため question → statement に変換
            quiz_data["statement"] = quiz_data["question"]
        else:
            logger.warning(f"クイズ {index} に statement も question もありません")
            return None
    
    # false_statement フィールドの確認（観測ログ）
    has_false_statement = "false_statement" in quiz_data and quiz_data.get("false_statement")
    if has_false_statement:
        false_stmt_preview = str(quiz_data["false_statement"])[:50]
        logger.info(f"クイズ {index} に false_statement が含まれています: {false_stmt_preview}...")
    
    # type のデフォルト値設定（○×固定）
    # 【修正】LLMがテンプレート名（T3、T6など）をtypeに入れてしまう場合があるため、チェックして修正
    if "type" not in quiz_data:
        quiz_data["type"] = "true_false"
    else:
        # typeがテンプレート名（T3、T6など）の場合は修正
        type_value = quiz_data.get("type", "")
        if isinstance(type_value, str) and type_value.startswith("T") and type_value[1:].isdigit():
            logger.warning(f"クイズ {index} のtypeがテンプレート名（{type_value}）になっています。'true_false'に修正します。")
            quiz_data["type"] = "true_false"
        elif type_value not in ["true_false", "mcq"]:
            logger.warning(f"クイズ {index} のtypeが不正な値（{type_value}）です。'true_false'に修正します。")
            quiz_data["type"] = "true_false"
    
    # 【重要】CitationはLLM出力に依存せず、コード側で必ず付与する
    # fallback_citations（実際には確定citation）を必ず使用し、最低1件を保証
    if fallback_citations and len(fallback_citations) > 0:
        # 確定citationを必ず使用（LLMが返したcitationsは無視）
        # 同一sourceのcitationを最大2件まで追加（複数根拠が必要な場合）
        final_citations = []
        
        # まず確定citation（fallback_citations[0]）を追加
        primary_citation = fallback_citations[0]
        
        # 【品質担保】citationのsourceとquoteの内容が一致しているか確認
        # 火災関連のキーワードが含まれている場合、sourceがsample*.txtでないことを確認
        # （火災関連の内容は「防犯・災害対応マニュアル（サンプル）.pdf」に含まれるべき）
        fire_keywords = ["火災", "避難", "災害", "防犯"]
        has_fire_content = any(keyword in primary_citation.quote for keyword in fire_keywords)
        
        # sample*.txtファイルに火災関連の内容が含まれている場合は不一致として検出
        if has_fire_content and primary_citation.source.startswith("sample") and primary_citation.source.endswith(".txt"):
            logger.error(
                f"[PARSE] 【重大】citationのsourceと内容の不一致を検出: "
                f"source={primary_citation.source}, quote_preview={primary_citation.quote[:100]}..., "
                f"fire_keywords={[kw for kw in fire_keywords if kw in primary_citation.quote]}, "
                f"index={index}"
            )
            # このcitationは除外する（誤ったsourceの可能性がある）
            # ただし、fallback_citationsが空になる場合はエラーを返す
            if len(fallback_citations) > 1:
                logger.warning(
                    f"[PARSE] 不一致citationをスキップし、次のcitationを使用します（index={index}）"
                )
                fallback_citations = fallback_citations[1:]
                primary_citation = fallback_citations[0]
            else:
                logger.error(
                    f"[PARSE] 【重大】不一致citationを除外するとfallback_citationsが空になります（index={index}）。"
                    f"このcitationは使用しませんが、エラーが発生する可能性があります。"
                )
                # この場合、citationを空にしてエラーを返す
                quiz_data["citations"] = []
                return None
        
        final_citations.append(primary_citation)
        
        # LLMが返したcitationsがある場合、同一sourceのもののみを最大1件追加
        if "citations" in quiz_data and isinstance(quiz_data["citations"], list) and len(quiz_data["citations"]) > 0:
            llm_citations = quiz_data["citations"]
            # 要素が全てdictかチェック
            if all(isinstance(item, dict) for item in llm_citations):
                for cit_data in llm_citations:
                    source = cit_data.get("source", "").strip()
                    quote = cit_data.get("quote", "").strip()
                    
                    # 同一sourceで、quoteが有効な場合のみ追加
                    if source == primary_citation.source and quote and len(final_citations) < 2:
                        final_citations.append(
                            Citation(
                                source=source,
                                page=cit_data.get("page"),
                                quote=quote,
                            )
                        )
                        logger.info(
                            f"クイズ {index}: LLM出力から同一sourceのcitationを追加 "
                            f"(source={source}, final_count={len(final_citations)})"
                        )
                        break  # 最大1件まで
        
        quiz_data["citations"] = final_citations
        logger.info(
            f"クイズ {index}: 確定citationを付与 "
            f"(source={primary_citation.source}, page={primary_citation.page}, final_count={len(final_citations)})"
        )
    else:
        # fallback_citationsがない場合は警告（通常は発生しない）
        logger.error(f"クイズ {index}: fallback_citationsが空です。citationsを空配列に設定します。")
        quiz_data["citations"] = []
    
    # QuizItemSchemaにパース
    quiz_item = QuizItemSchema(**quiz_data)
    return quiz_item
