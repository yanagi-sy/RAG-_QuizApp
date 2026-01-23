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
    
    # Citationをパース（LLMが返した場合）
    if "citations" in quiz_data and isinstance(quiz_data["citations"], list):
        # 空配列チェック（LLMが [] を返した場合）
        if len(quiz_data["citations"]) == 0:
            logger.warning(f"クイズ {index} の citations が空配列、fallback_citations を採用")
            quiz_data["citations"] = fallback_citations[:3] if fallback_citations else []
        else:
            # 要素が全てdictかチェック（list[str]などの不正形式を検出）
            all_dict = all(isinstance(item, dict) for item in quiz_data["citations"])
            
            if not all_dict:
                # 要素にdict以外が混ざっている場合、LLM出力は捨ててfallbackを使用
                # dict以外の要素を特定して詳細をログに記録
                non_dict_items = [
                    {"index": i, "type": type(item).__name__, "value": str(item)[:50]} 
                    for i, item in enumerate(quiz_data["citations"]) 
                    if not isinstance(item, dict)
                ]
                logger.warning(
                    f"クイズ {index} の citations に dict 以外の要素: {non_dict_items}、"
                    f"fallback_citations を採用"
                )
                quiz_data["citations"] = fallback_citations[:3] if fallback_citations else []
            else:
                # 全てdictの場合は従来通り処理
                parsed_citations = []
                for cit_data in quiz_data["citations"]:
                    # source と quote の両方をチェック
                    source = cit_data.get("source", "").strip()
                    quote = cit_data.get("quote", "").strip()
                    
                    # source または quote が空の場合は fallback_citations を使う
                    if (not source or not quote) and fallback_citations:
                        logger.warning(
                            f"クイズ {index} の citation に空フィールド（source={bool(source)}, quote={bool(quote)}）、"
                            f"fallback を使用"
                        )
                        # fallback_citations から該当するものを探す（source が一致するもの）
                        if source:
                            fallback = next((c for c in fallback_citations if c.source == source), fallback_citations[0])
                        else:
                            fallback = fallback_citations[0]
                        
                        source = fallback.source
                        quote = fallback.quote
                    
                    parsed_citations.append(
                        Citation(
                            source=source,
                            page=cit_data.get("page"),
                            quote=quote,
                        )
                    )
                
                # parsed_citations が空の場合もfallbackを使用（安全策）
                quiz_data["citations"] = parsed_citations if parsed_citations else fallback_citations[:1]
    else:
        # citationsがない場合はfallbackを使用
        logger.warning(f"クイズ {index} に citations がないため、fallback_citations を採用")
        quiz_data["citations"] = fallback_citations[:1] if fallback_citations else []
    
    # QuizItemSchemaにパース
    quiz_item = QuizItemSchema(**quiz_data)
    return quiz_item
