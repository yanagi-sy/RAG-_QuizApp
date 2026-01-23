"""
Quiz APIルーター
"""
import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, List
from fastapi import APIRouter, HTTPException, Query

from app.schemas.quiz import (
    QuizRequest,
    QuizResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizSetMetadata,
    QuizSet,
    QuizSetListResponse,
)
from app.schemas.common import Citation
from app.core.settings import settings
from app.quiz.retrieval import retrieve_for_quiz
from app.quiz.generation_handler import generate_quizzes_with_retry
from app.quiz.debug_builder import build_error_response, build_debug_response
from app.quiz import store as quiz_store

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


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

    # ダミー実装: quiz_idは固定値を返す（保存しない）
    quiz_id = "dummy-quiz-id"

    # レスポンスを返す
    return QuizResponse(
        quiz_id=quiz_id,
        question=question,
    )


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quizzes_endpoint(request: QuizGenerateRequest) -> QuizGenerateResponse:
    """
    根拠付きクイズを生成する（教材サンプリング方式）
    
    検索ではなく「教材からサンプリングして出題」する。
    全資料 / 任意の単独資料 / 全難易度で必ず count 件生成できる。
    
    Args:
        request: クイズ生成リクエスト
        
    Returns:
        生成されたクイズのリスト
    """
    # タイミング計測開始
    t_start = time.perf_counter()
    
    # request_id を生成（uuid短縮版、全attemptで共通）
    request_id = str(uuid.uuid4())[:8]
    
    logger.info(
        f"[QUIZ_GENERATE:START] request_id={request_id}, "
        f"level={request.level}, count={request.count}, save={request.save}"
    )
    
    # クイズ専用の候補取得（サンプリング方式、タイミング計測付き）
    t_retrieval_start = time.perf_counter()
    logger.info(f"[RETRIEVAL:START]")
    citations, quiz_debug_info = retrieve_for_quiz(
        source_ids=request.source_ids,
        level=request.level,
        count=request.count,
        debug=request.debug
    )
    t_retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
    logger.info(f"[RETRIEVAL:DONE] {t_retrieval_ms:.1f}ms, citations={len(citations)}")
    
    # 引用が0件の場合はエラーを返す
    if len(citations) == 0:
        final_debug = build_error_response(
            request, quiz_debug_info,
            "引用が見つかりませんでした"
        )
        return QuizGenerateResponse(
            quizzes=[],
            debug=final_debug,
        )
    
    # CHANGED: クイズセット機能では5問が必要なため、最大5問に変更
    target_count = min(request.count, 5)
    logger.info(f"Quiz生成目標: target={target_count}（最大5問、req.count={request.count}）, citations={len(citations)}件")
    
    # LLMでクイズを生成（バリデーション付き）
    t_llm_start = time.perf_counter()
    logger.info(f"[LLM:START] request_id={request_id}, target_count={target_count}")
    accepted_quizzes, rejected_items, error_info, attempts, attempt_errors, aggregated_stats = await generate_quizzes_with_retry(
        request, target_count, citations, request_id
    )
    t_llm_ms = (time.perf_counter() - t_llm_start) * 1000
    logger.info(f"[LLM:DONE] {t_llm_ms:.1f}ms, accepted={len(accepted_quizzes)}, attempts={attempts}")
    
    # 全体のタイミング計測
    t_total_ms = (time.perf_counter() - t_start) * 1000
    
    # debugレスポンスを構築
    final_debug = build_debug_response(
        request, quiz_debug_info, target_count,
        len(citations), len(accepted_quizzes), rejected_items, error_info, attempts,
        attempt_errors, aggregated_stats, t_retrieval_ms, t_llm_ms, t_total_ms
    )
    
    # クイズセットを保存（save=true の場合）
    quiz_set_id = None
    t_save_ms = 0.0
    if request.save and len(accepted_quizzes) > 0:
        t_save_start = time.perf_counter()
        logger.info(f"[SAVE:START] quizzes_count={len(accepted_quizzes)}")
        try:
            # quizzes を dict に変換
            quizzes_dict = [
                quiz.model_dump() if hasattr(quiz, "model_dump") else quiz.dict()
                for quiz in accepted_quizzes
            ]
            
            # 保存
            payload = {
                "quizzes": quizzes_dict,
                "source_ids": request.source_ids,
                "level": request.level,
                "count": len(accepted_quizzes),
                "debug": final_debug,
            }
            quiz_set_id = quiz_store.save_quiz_set(payload)
            t_save_ms = (time.perf_counter() - t_save_start) * 1000
            logger.info(f"[SAVE:DONE] {t_save_ms:.1f}ms, quiz_set_id={quiz_set_id}")
            
        except Exception as e:
            t_save_ms = (time.perf_counter() - t_save_start) * 1000
            logger.error(f"[SAVE:ERROR] {t_save_ms:.1f}ms, error={e}")
            # 保存失敗してもクイズ生成結果は返す
    
    # 全体のタイミング（save含む）
    t_total_with_save_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"[QUIZ_GENERATE:DONE] total={t_total_with_save_ms:.1f}ms "
        f"(retrieval={t_retrieval_ms:.1f}ms, llm={t_llm_ms:.1f}ms, save={t_save_ms:.1f}ms), "
        f"quizzes={len(accepted_quizzes)}, quiz_set_id={quiz_set_id}"
    )
    
    return QuizGenerateResponse(
        quizzes=accepted_quizzes,
        quiz_set_id=quiz_set_id,
        debug=final_debug,
    )


# --- QuizSet保存/取得API ---

@router.get("/sets", response_model=QuizSetListResponse)
async def list_quiz_sets(
    level: Optional[str] = Query(None, description="難易度でフィルタ"),
    source_ids: Optional[List[str]] = Query(None, description="ソースIDでフィルタ"),
    limit: int = Query(50, ge=1, le=100, description="取得件数上限")
) -> QuizSetListResponse:
    """
    保存済みQuizSetの一覧を取得する
    
    Args:
        level: 難易度でフィルタ（None=全て）
        source_ids: ソースIDでフィルタ（None=全て）
        limit: 取得件数上限（1-100）
        
    Returns:
        QuizSetのメタデータリスト
    """
    try:
        quiz_sets = quiz_store.list_quiz_sets(
            level=level,
            source_ids=source_ids,
            limit=limit
        )
        
        # Pydantic スキーマに変換
        metadata_list = [QuizSetMetadata(**qs) for qs in quiz_sets]
        
        return QuizSetListResponse(
            quiz_sets=metadata_list,
            total=len(metadata_list)
        )
        
    except Exception as e:
        logger.error(f"Failed to list quiz sets: {e}")
        raise HTTPException(status_code=500, detail="クイズセット一覧の取得に失敗しました")


@router.get("/sets/{quiz_set_id}", response_model=QuizSet)
async def get_quiz_set(quiz_set_id: str) -> QuizSet:
    """
    QuizSetを1件取得する
    
    Args:
        quiz_set_id: QuizSet ID
        
    Returns:
        QuizSet全体（quizzes含む）
    """
    try:
        quiz_set_data = quiz_store.load_quiz_set(quiz_set_id)
        
        if quiz_set_data is None:
            raise HTTPException(status_code=404, detail="QuizSetが見つかりません")
        
        # Pydantic スキーマに変換
        return QuizSet(**quiz_set_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load quiz set {quiz_set_id}: {e}")
        raise HTTPException(status_code=500, detail="QuizSetの取得に失敗しました")


@router.delete("/sets/{quiz_set_id}")
async def delete_quiz_set(quiz_set_id: str) -> dict:
    """
    QuizSetを削除する
    
    Args:
        quiz_set_id: QuizSet ID
        
    Returns:
        削除結果
    """
    try:
        success = quiz_store.delete_quiz_set(quiz_set_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="QuizSetが見つかりません")
        
        return {"message": "QuizSetを削除しました", "quiz_set_id": quiz_set_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete quiz set {quiz_set_id}: {e}")
        raise HTTPException(status_code=500, detail="QuizSetの削除に失敗しました")
