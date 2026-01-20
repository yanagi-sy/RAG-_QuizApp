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
) -> tuple[list[QuizItemSchema], str | None, str]:
    """
    LLMレスポンスからクイズをパース（○×問題専用、堅牢化版）
    
    - 空応答チェック
    - コードフェンス優先抽出
    - 先頭/末尾の余計な文字除去
    - JSON形式のパース（best effort）
    - statement フィールドの確認（question も互換性のため許容）
    - UUIDの生成
    
    Args:
        response_text: LLMからのレスポンステキスト
        fallback_citations: パースに失敗した場合のフォールバック引用
        
    Returns:
        (items, parse_error, raw_excerpt) のタプル
        - items: パースされたクイズのリスト
        - parse_error: パースエラー文字列（成功時はNone）
        - raw_excerpt: レスポンステキストの先頭200文字（debug用）
    """
    # raw_excerpt を保存（debug用）
    raw_excerpt = response_text[:200] if response_text else ""
    
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
    
    # 各クイズをパース
    quizzes = []
    for i, quiz_data in enumerate(quizzes_data):
        try:
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
    
    # type のデフォルト値設定（○×固定）
    if "type" not in quiz_data:
        quiz_data["type"] = "true_false"
    
    # Citationをパース（LLMが返した場合）
    if "citations" in quiz_data and isinstance(quiz_data["citations"], list):
        parsed_citations = []
        for cit_data in quiz_data["citations"]:
            # quote が空の場合は fallback_citations を使う
            quote = cit_data.get("quote", "").strip()
            if not quote and fallback_citations:
                # fallback_citations から該当するものを探す（source が一致するもの）
                source = cit_data.get("source", "")
                fallback = next((c for c in fallback_citations if c.source == source), fallback_citations[0] if fallback_citations else None)
                if fallback:
                    quote = fallback.quote
            
            parsed_citations.append(
                Citation(
                    source=cit_data.get("source", ""),
                    page=cit_data.get("page"),
                    quote=quote,
                )
            )
        quiz_data["citations"] = parsed_citations if parsed_citations else fallback_citations[:1]
    else:
        # citationsがない場合はfallbackを使用
        quiz_data["citations"] = fallback_citations[:1] if fallback_citations else []
    
    # QuizItemSchemaにパース
    quiz_item = QuizItemSchema(**quiz_data)
    return quiz_item
