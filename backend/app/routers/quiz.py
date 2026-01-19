"""
Quiz APIルーター
"""
import asyncio
import json
import logging
import uuid
from typing import Dict, Any
from fastapi import APIRouter

from app.quiz.store import QuizItem, save_quiz
from app.schemas.quiz import (
    QuizRequest,
    QuizResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizItem as QuizItemSchema,
)
from app.schemas.common import Citation
from app.core.settings import settings
from app.llm.base import LLMInternalError, LLMTimeoutError
from app.llm.ollama import get_ollama_client
from app.llm.prompt import build_quiz_generation_messages
from app.routers.ask import _hybrid_retrieval

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


def validate_quiz_item(item: dict) -> tuple[bool, str]:
    """
    クイズアイテムをバリデーション（○×問題専用）
    
    検証項目:
    - type が "true_false" であること
    - statement に "?" "？" が含まれないこと
    - answer_bool が bool であること
    - citations が1件以上あること
    - citations の source/page/quote が欠けていないこと
    
    Args:
        item: クイズアイテム（dict）
        
    Returns:
        (ok: bool, reason: str) のタプル
    """
    # type チェック
    if item.get("type") != "true_false":
        return (False, f"type が true_false ではありません: {item.get('type')}")
    
    # statement チェック（必須、疑問形禁止）
    statement = item.get("statement")
    if not statement or not isinstance(statement, str):
        return (False, "statement が文字列ではありません")
    
    if "?" in statement or "？" in statement:
        return (False, f"statement に疑問符が含まれています: {statement[:50]}")
    
    # answer_bool チェック（必須、bool型）
    answer_bool = item.get("answer_bool")
    if answer_bool is None or not isinstance(answer_bool, bool):
        return (False, f"answer_bool が bool ではありません: {answer_bool}")
    
    # citations チェック（1件以上）
    citations = item.get("citations")
    if not citations or not isinstance(citations, list) or len(citations) == 0:
        return (False, "citations が空です")
    
    # citations の中身をチェック
    for i, cit in enumerate(citations):
        if not isinstance(cit, dict):
            return (False, f"citations[{i}] が辞書ではありません")
        
        if not cit.get("source"):
            return (False, f"citations[{i}].source が空です")
        
        if not cit.get("quote"):
            return (False, f"citations[{i}].quote が空です")
        
        # page は null でも OK（txt の場合）
    
    return (True, "")


@router.post("", response_model=QuizResponse)
async def create_quiz(request: QuizRequest) -> QuizResponse:
    """
    クイズを出題する（ダミー実装）

    - level: 必須。beginner/intermediate/advancedのいずれか
    """
    # ローディング確認用の遅延
    await asyncio.sleep(0.8)

    # levelに応じた問題文を生成（ダミー）
    level_texts = {
        "beginner": "初級",
        "intermediate": "中級",
        "advanced": "上級",
    }
    level_text = level_texts.get(request.level, "初級")
    question = f"○×：（ダミー）{level_text}レベルの問題です。最初にAを実行する。"

    # クイズアイテムを作成（正解はtrue固定）
    quiz_item = QuizItem(
        question=question,
        correct_answer=True,
        explanation="（ダミー）解説です。",
        citations=[
            Citation(
                source="dummy.txt",
                page=1,
                quote="（ダミー）引用です。",
            )
        ],
    )

    # storeに保存してquiz_idを取得
    quiz_id = save_quiz(quiz_item)

    # レスポンスを返す
    return QuizResponse(
        quiz_id=quiz_id,
        question=question,
    )


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quizzes(request: QuizGenerateRequest) -> QuizGenerateResponse:
    """
    根拠付きクイズを生成する
    
    - level, topicから検索クエリを作成
    - 既存の _hybrid_retrieval で引用を取得
    - LLMでJSON形式のクイズを生成
    - 引用に基づくクイズのみを返す
    
    Args:
        request: クイズ生成リクエスト
        
    Returns:
        生成されたクイズのリスト
    """
    # 検索クエリを構築（topic + level）
    search_query = _build_search_query(request.level, request.topic)
    logger.info(f"Quiz生成用検索クエリ: {search_query}")
    
    # NEW: source_ids をそのまま allowed_sources として使用（変換不要）
    allowed_sources = request.source_ids if request.source_ids else None
    logger.info(f"[DEBUG] request.source_ids = {request.source_ids}")
    logger.info(f"[DEBUG] allowed_sources = {allowed_sources}")
    if allowed_sources:
        logger.info(f"検索対象資料を絞り込み: {allowed_sources}")
    
    # 検索パラメータ
    semantic_weight = 0.5  # デフォルト
    if request.retrieval and request.retrieval.semantic_weight is not None:
        semantic_weight = request.retrieval.semantic_weight
        semantic_weight = max(0.0, min(1.0, semantic_weight))
    
    keyword_weight = 1.0 - semantic_weight
    
    # 既存の _hybrid_retrieval で引用を取得（source_filter を追加）
    citations = []
    debug_info = None
    try:
        citations, debug_info = _hybrid_retrieval(
            query=search_query,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            top_k=settings.top_k,
            include_debug=request.debug,
            source_filter=allowed_sources,
        )
        logger.info(f"Hybrid retrieval完了: {len(citations)}件の引用を取得")
    except Exception as e:
        logger.warning(f"Hybrid retrievalに失敗しました: {type(e).__name__}: {e}")
        # 引用が取得できない場合はエラーレスポンスを返す（debug情報を含める）
        final_debug = None
        if request.debug:
            final_debug = debug_info or {}
            # _post_rerank_with_textは内部情報なので削除
            if "_post_rerank_with_text" in final_debug:
                del final_debug["_post_rerank_with_text"]
            final_debug["request_source_ids"] = request.source_ids
            final_debug["search_query"] = search_query
            final_debug["error"] = f"検索に失敗しました: {str(e)}"
        
        return QuizGenerateResponse(
            quizzes=[],
            debug=final_debug,
        )
    
    # 引用が少ない場合はcountを調整
    if len(citations) == 0:
        logger.warning("引用が見つかりませんでした。救済ロジックを試行します。")
        
        # NEW: Quiz救済ロジック（閾値で全落ちした場合に、次善の根拠を採用）
        quiz_fallback_used = False
        quiz_fallback_reason = None
        quiz_fallback_selected = []
        
        if debug_info and "_post_rerank_with_text" in debug_info:
            post_rerank_with_text = debug_info["_post_rerank_with_text"]
            
            if len(post_rerank_with_text) > 0:
                # 先頭からQUIZ_FALLBACK_TOP_N件を取得して仮citationsを構築
                fallback_count = min(settings.quiz_fallback_top_n, len(post_rerank_with_text))
                
                for item in post_rerank_with_text[:fallback_count]:
                    source = item["source"]
                    page = item.get("page")
                    text = item["text"]
                    rerank_score = item["rerank_score"]
                    
                    # pageの扱い：txtはnull、pdfは1以上をそのまま返す
                    page_value = page if page is not None and page > 0 else None
                    
                    # quoteは先頭400文字で切る（quiz生成用の最小抜粋）
                    quote = text[:400] if len(text) > 400 else text
                    
                    citations.append(
                        Citation(
                            source=source,
                            page=page_value,
                            quote=quote,
                        )
                    )
                    
                    quiz_fallback_selected.append({
                        "source": source,
                        "page": page_value,
                        "rerank_score": rerank_score,
                    })
                
                quiz_fallback_used = True
                quiz_fallback_reason = "citations_zero_after_threshold"
                logger.info(
                    f"Quiz救済ロジック適用: {len(citations)}件の引用を採用（post_rerankから取得）"
                )
        
        # 救済後もcitationsが0件の場合はエラーを返す
        if len(citations) == 0:
            # debug情報を構築（ask側のdebugを含める）
            final_debug = None
            if request.debug:
                final_debug = debug_info or {}
                final_debug["request_source_ids"] = request.source_ids
                final_debug["search_query"] = search_query
                final_debug["error"] = "引用が見つかりませんでした（救済ロジックも失敗）"
                final_debug["quiz_fallback_used"] = quiz_fallback_used
            
            return QuizGenerateResponse(
                quizzes=[],
                debug=final_debug,
            )
        
        # 救済成功時はdebug情報に追加（後でfinal_debugに統合）
        if request.debug and quiz_fallback_used:
            if debug_info is None:
                debug_info = {}
            debug_info["quiz_fallback_used"] = quiz_fallback_used
            debug_info["quiz_fallback_reason"] = quiz_fallback_reason
            debug_info["quiz_fallback_selected"] = quiz_fallback_selected
    
    # 引用が少ない場合は生成数を減らす
    adjusted_count = min(request.count, max(1, len(citations) // 2))
    if adjusted_count < request.count:
        logger.info(f"引用数が少ないため、生成数を {request.count} → {adjusted_count} に調整")
    
    # LLMでクイズを生成（バリデーション付き、最大2回試行）
    accepted_quizzes = []
    rejected_items = []
    llm_error = None
    total_generated = 0
    
    # 1回目の生成
    try:
        quizzes, rejected = await _generate_and_validate_quizzes(
            level=request.level,
            count=adjusted_count,
            topic=request.topic,
            citations=citations,
        )
        accepted_quizzes.extend(quizzes)
        rejected_items.extend(rejected)
        total_generated += len(quizzes) + len(rejected)
        
        logger.info(
            f"Quiz生成1回目: generated={len(quizzes) + len(rejected)}, "
            f"accepted={len(quizzes)}, rejected={len(rejected)}"
        )
    except Exception as e:
        logger.error(f"Quiz生成1回目に失敗: {type(e).__name__}: {e}")
        llm_error = str(e)
    
    # 不足時は2回目の生成（最大1回だけ再試行）
    if len(accepted_quizzes) < adjusted_count and llm_error is None:
        remaining_count = adjusted_count - len(accepted_quizzes)
        logger.info(f"不足分を再生成: remaining={remaining_count}")
        
        try:
            quizzes_2, rejected_2 = await _generate_and_validate_quizzes(
                level=request.level,
                count=remaining_count,
                topic=request.topic,
                citations=citations,
            )
            accepted_quizzes.extend(quizzes_2)
            rejected_items.extend(rejected_2)
            total_generated += len(quizzes_2) + len(rejected_2)
            
            logger.info(
                f"Quiz生成2回目: generated={len(quizzes_2) + len(rejected_2)}, "
                f"accepted={len(quizzes_2)}, rejected={len(rejected_2)}"
            )
        except Exception as e:
            logger.error(f"Quiz生成2回目に失敗: {type(e).__name__}: {e}")
            if not llm_error:
                llm_error = str(e)
    
    # debugレスポンスを構築
    final_debug = None
    if request.debug:
        final_debug = debug_info or {}
        
        # _post_rerank_with_textは内部情報なので削除
        if "_post_rerank_with_text" in final_debug:
            del final_debug["_post_rerank_with_text"]
        
        # リクエスト情報を追加（先頭に配置）
        final_debug["request_source_ids"] = request.source_ids
        final_debug["search_query"] = search_query
        final_debug["adjusted_count"] = adjusted_count
        final_debug["generated_count"] = total_generated
        final_debug["accepted_count"] = len(accepted_quizzes)
        final_debug["rejected_count"] = len(rejected_items)
        
        # rejected_reasons を集計
        rejected_reasons: Dict[str, int] = {}
        for item in rejected_items:
            reason = item.get("reason", "unknown")
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
        final_debug["rejected_reasons"] = rejected_reasons
        
        # sample_rejected（先頭1〜2件）
        if len(rejected_items) > 0:
            final_debug["sample_rejected"] = rejected_items[:2]
        
        if llm_error:
            final_debug["llm_error"] = llm_error
    
    return QuizGenerateResponse(
        quizzes=accepted_quizzes,
        debug=final_debug,
    )


def _build_search_query(
    level: str,
    topic: str | None,
) -> str:
    """
    Quiz生成用の検索クエリを構築
    
    - topicがあればtopicを含める
    - levelに応じてクエリを調整
    
    Args:
        level: 難易度
        topic: トピック（オプション）
        
    Returns:
        検索クエリ文字列
    """
    # levelに応じたキーワード
    level_keywords = {
        "beginner": "基本 ルール 手順 共通",
        "intermediate": "理由 方法 適用 実務",
        "advanced": "例外 禁止 判断基準 注意",
    }
    
    level_keyword = level_keywords.get(level, "基本 ルール")
    
    # topicがあればtopicを優先
    if topic:
        return f"{topic} {level_keyword}"
    else:
        return level_keyword


async def _generate_and_validate_quizzes(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
) -> tuple[list[QuizItemSchema], list[dict]]:
    """
    LLMでクイズを生成し、バリデーションを行う
    
    Args:
        level: 難易度
        count: 生成数
        topic: トピック
        citations: 引用リスト
        
    Returns:
        (accepted_quizzes, rejected_items) のタプル
        - accepted_quizzes: バリデーション通過したクイズのリスト
        - rejected_items: バリデーション失敗したアイテム情報のリスト
    """
    # LLMで生成（JSONパースまで）
    raw_quizzes = await _generate_quizzes_with_llm(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
    )
    
    # バリデーション
    accepted = []
    rejected = []
    
    for quiz in raw_quizzes:
        # dict に変換してバリデーション
        quiz_dict = quiz.model_dump() if hasattr(quiz, "model_dump") else quiz.dict()
        ok, reason = validate_quiz_item(quiz_dict)
        
        if ok:
            accepted.append(quiz)
        else:
            logger.warning(f"Quiz バリデーション失敗: {reason}")
            rejected.append({
                "statement": quiz_dict.get("statement", quiz_dict.get("question", ""))[:100],
                "reason": reason,
            })
    
    return (accepted, rejected)


async def _generate_quizzes_with_llm(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
) -> list[QuizItemSchema]:
    """
    LLMでクイズを生成
    
    - JSON形式で出力（厳守）
    - 引用に基づくクイズのみ
    - パース失敗時は再試行（1回まで）
    
    Args:
        level: 難易度
        count: 生成数
        topic: トピック
        citations: 引用リスト
        
    Returns:
        生成されたクイズのリスト
        
    Raises:
        LLMTimeoutError: タイムアウト
        LLMInternalError: LLMエラー
        ValueError: JSONパースエラー
    """
    # LLMクライアントを取得
    llm_client = get_ollama_client()
    
    # プロンプトを構築
    messages = build_quiz_generation_messages(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
    )
    
    # LLMで生成（最大2回試行）
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # LLMで生成
            response_text = await asyncio.wait_for(
                llm_client.chat(messages=messages),
                timeout=settings.ollama_timeout_sec * 2,  # Quiz生成は時間がかかるので2倍
            )
            
            logger.info(f"LLMレスポンス取得成功（試行 {attempt + 1}/{max_retries}）")
            
            # JSONパース
            quizzes = _parse_quiz_json(response_text, citations)
            
            if len(quizzes) > 0:
                return quizzes
            else:
                logger.warning("生成されたクイズが0件でした")
                if attempt < max_retries - 1:
                    logger.info("再試行します")
                    continue
                else:
                    raise ValueError("クイズの生成に失敗しました（0件）")
        
        except (LLMTimeoutError, asyncio.TimeoutError) as e:
            logger.warning(f"LLMタイムアウト（試行 {attempt + 1}/{max_retries}）: {e}")
            if attempt < max_retries - 1:
                continue
            else:
                raise LLMTimeoutError("Quiz生成がタイムアウトしました")
        
        except (LLMInternalError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"LLMエラーまたはJSONパースエラー（試行 {attempt + 1}/{max_retries}）: {e}")
            if attempt < max_retries - 1:
                continue
            else:
                raise ValueError(f"Quiz生成に失敗しました: {str(e)}")
    
    # ここには到達しないはずだが、念のため
    raise ValueError("Quiz生成に失敗しました（不明なエラー）")


def _parse_quiz_json(
    response_text: str,
    fallback_citations: list[Citation],
) -> list[QuizItemSchema]:
    """
    LLMレスポンスからクイズをパース（○×問題専用）
    
    - JSON形式のパース
    - statement フィールドの確認（question も互換性のため許容）
    - UUIDの生成
    
    Args:
        response_text: LLMからのレスポンステキスト
        fallback_citations: パースに失敗した場合のフォールバック引用
        
    Returns:
        パースされたクイズのリスト
        
    Raises:
        json.JSONDecodeError: JSONパースエラー
        ValueError: バリデーションエラー
    """
    # JSONブロックを抽出（```json ... ``` の場合）
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]  # "```json" を削除
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # "```" を削除
        response_text = response_text.strip()
    elif response_text.startswith("```"):
        response_text = response_text[3:]  # "```" を削除
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # "```" を削除
        response_text = response_text.strip()
    
    # JSONパース
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {e}")
        logger.error(f"レスポンステキスト（先頭500文字）: {response_text[:500]}")
        raise
    
    # quizzesキーの確認
    if "quizzes" not in data:
        raise ValueError("JSONに 'quizzes' キーが含まれていません")
    
    quizzes_data = data["quizzes"]
    if not isinstance(quizzes_data, list):
        raise ValueError("'quizzes' はリストである必要があります")
    
    # 各クイズをパース
    quizzes = []
    for i, quiz_data in enumerate(quizzes_data):
        try:
            # IDを生成（LLMが返さない場合）
            if "id" not in quiz_data or not quiz_data["id"]:
                quiz_data["id"] = str(uuid.uuid4())[:8]  # 短いID
            
            # statement フィールドの確認（question も互換性のため許容）
            if "statement" not in quiz_data:
                if "question" in quiz_data:
                    # 互換性のため question → statement に変換
                    quiz_data["statement"] = quiz_data["question"]
                else:
                    logger.warning(f"クイズ {i} に statement も question もありません")
                    continue
            
            # type のデフォルト値設定（○×固定）
            if "type" not in quiz_data:
                quiz_data["type"] = "true_false"
            
            # Citationをパース（LLMが返した場合）
            if "citations" in quiz_data and isinstance(quiz_data["citations"], list):
                parsed_citations = []
                for cit_data in quiz_data["citations"]:
                    parsed_citations.append(
                        Citation(
                            source=cit_data.get("source", ""),
                            page=cit_data.get("page"),
                            quote=cit_data.get("quote", ""),
                        )
                    )
                quiz_data["citations"] = parsed_citations
            else:
                # citationsがない場合はfallbackを使用
                quiz_data["citations"] = fallback_citations[:1]  # 最初の1件
            
            # QuizItemSchemaにパース
            quiz_item = QuizItemSchema(**quiz_data)
            quizzes.append(quiz_item)
            
        except Exception as e:
            logger.warning(f"クイズ {i} のパースに失敗: {e}")
            # パースに失敗したクイズはスキップ
            continue
    
    return quizzes
