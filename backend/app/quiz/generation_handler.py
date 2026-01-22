"""
Quiz生成の再試行ロジック

generate_and_validate_quizzes を呼び出して、複数回試行する。
"""
import logging
from typing import Dict, Any

from app.schemas.quiz import QuizGenerateRequest, QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.quiz.generator import generate_and_validate_quizzes
from app.core.settings import settings

# ロガー設定
logger = logging.getLogger(__name__)


async def generate_quizzes_with_retry(
    request: QuizGenerateRequest,
    target_count: int,
    citations: list[Citation],
    request_id: str,
) -> tuple[list[QuizItemSchema], list[dict], dict, int, list[dict], dict]:
    """
    クイズ生成を再試行する（複数回試行）
    
    Args:
        request: クイズ生成リクエスト
        target_count: 目標生成数
        citations: 引用リスト
        request_id: リクエストID
        
    Returns:
        (accepted_quizzes, rejected_items, error_info, attempts, attempt_errors, aggregated_stats) のタプル
        - accepted_quizzes: 採用されたクイズのリスト
        - rejected_items: バリデーション失敗したアイテム情報のリスト
        - error_info: エラー情報（最終失敗時）
        - attempts: 試行回数
        - attempt_errors: 試行ごとの失敗履歴
        - aggregated_stats: 集計統計情報
    """
    max_attempts = settings.quiz_max_attempts
    accepted_quizzes = []
    all_rejected_items = []
    all_attempt_errors = []
    aggregated_stats = {}
    
    # 目標数に達するまで、または最大試行回数に達するまで繰り返す
    attempts = 0
    while len(accepted_quizzes) < target_count and attempts < max_attempts:
        attempts += 1
        
        # 残り必要数
        remaining = target_count - len(accepted_quizzes)
        
        logger.info(
            f"[GENERATION_RETRY] attempt={attempts}/{max_attempts}, "
            f"accepted={len(accepted_quizzes)}, target={target_count}, remaining={remaining}"
        )
        
        try:
            # 1問ずつ生成（generate_and_validate_quizzesはcount=1専用）
            batch_accepted, batch_rejected, batch_attempt_errors, batch_stats = await generate_and_validate_quizzes(
                level=request.level,
                count=1,  # 1問ずつ生成
                topic=request.topic,
                citations=citations,
                request_id=request_id,
                attempt_index=attempts,
            )
            
            # 結果を集計
            accepted_quizzes.extend(batch_accepted)
            all_rejected_items.extend(batch_rejected)
            all_attempt_errors.extend(batch_attempt_errors)
            
            # 統計情報をマージ
            for key, value in batch_stats.items():
                if key in aggregated_stats:
                    if isinstance(value, (int, float)):
                        aggregated_stats[key] += value
                    elif isinstance(value, dict):
                        # dictの場合はマージ
                        for k, v in value.items():
                            aggregated_stats[key][k] = aggregated_stats[key].get(k, 0) + (v if isinstance(v, (int, float)) else 0)
                else:
                    aggregated_stats[key] = value
            
            logger.info(
                f"[GENERATION_RETRY] attempt={attempts} 完了: "
                f"accepted={len(batch_accepted)}, rejected={len(batch_rejected)}, "
                f"total_accepted={len(accepted_quizzes)}"
            )
            
        except Exception as e:
            logger.error(f"[GENERATION_RETRY] attempt={attempts} でエラー: {type(e).__name__}: {e}")
            
            # エラー情報を記録
            all_attempt_errors.append({
                "attempt": attempts,
                "stage": "generation",
                "type": type(e).__name__,
                "message": str(e),
            })
            
            # 最大試行回数に達した場合は終了
            if attempts >= max_attempts:
                break
    
    # 目標数に達したかどうか
    exhausted = len(accepted_quizzes) < target_count
    
    # エラー情報を構築
    error_info = None
    if exhausted and len(accepted_quizzes) == 0:
        error_info = {
            "type": "generation_failed",
            "message": f"最大試行回数（{max_attempts}回）に達しましたが、クイズが生成できませんでした",
        }
    elif exhausted:
        error_info = {
            "type": "partial_success",
            "message": f"目標数（{target_count}問）に達しませんでした（生成数: {len(accepted_quizzes)}問）",
        }
    
    # 最終的な統計情報
    aggregated_stats["attempts"] = attempts
    aggregated_stats["exhausted"] = exhausted
    aggregated_stats["generated_count"] = len(accepted_quizzes)
    aggregated_stats["target_count"] = target_count
    
    logger.info(
        f"[GENERATION_RETRY] 完了: "
        f"attempts={attempts}, accepted={len(accepted_quizzes)}, target={target_count}, "
        f"exhausted={exhausted}"
    )
    
    return (
        accepted_quizzes,
        all_rejected_items,
        error_info,
        attempts,
        all_attempt_errors,
        aggregated_stats,
    )
