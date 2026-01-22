"""
Quiz生成のデバッグ情報構築

エラーレスポンスとデバッグレスポンスを構築する。
"""
import logging
from typing import Dict, Any, Optional

from app.schemas.quiz import QuizGenerateRequest

# ロガー設定
logger = logging.getLogger(__name__)


def build_error_response(
    request: QuizGenerateRequest,
    quiz_debug_info: Optional[Dict[str, Any]],
    error_message: str,
) -> Dict[str, Any]:
    """
    エラーレスポンスを構築
    
    Args:
        request: クイズ生成リクエスト
        quiz_debug_info: クイズデバッグ情報（retrieval側から）
        error_message: エラーメッセージ
        
    Returns:
        デバッグ情報の辞書
    """
    debug_info: Dict[str, Any] = {
        "error": {
            "type": "retrieval_failed",
            "message": error_message,
        },
    }
    
    # retrieval側のデバッグ情報があれば追加
    if quiz_debug_info:
        debug_info.update(quiz_debug_info)
    
    # リクエスト情報を追加
    debug_info["request"] = {
        "level": request.level,
        "count": request.count,
        "topic": request.topic,
        "source_ids": request.source_ids,
    }
    
    return debug_info


def build_debug_response(
    request: QuizGenerateRequest,
    quiz_debug_info: Optional[Dict[str, Any]],
    target_count: int,
    citations_count: int,
    accepted_count: int,
    rejected_items: list[dict],
    error_info: Optional[Dict[str, Any]],
    attempts: int,
    attempt_errors: list[dict],
    aggregated_stats: Dict[str, Any],
    t_retrieval_ms: float,
    t_llm_ms: float,
    t_total_ms: float,
) -> Dict[str, Any]:
    """
    デバッグレスポンスを構築
    
    Args:
        request: クイズ生成リクエスト
        quiz_debug_info: クイズデバッグ情報（retrieval側から）
        target_count: 目標生成数
        citations_count: 引用数
        accepted_count: 採用されたクイズ数
        rejected_items: バリデーション失敗したアイテム情報のリスト
        error_info: エラー情報
        attempts: 試行回数
        attempt_errors: 試行ごとの失敗履歴
        aggregated_stats: 集計統計情報
        t_retrieval_ms: retrieval処理時間（ミリ秒）
        t_llm_ms: LLM処理時間（ミリ秒）
        t_total_ms: 全体処理時間（ミリ秒）
        
    Returns:
        デバッグ情報の辞書
    """
    debug_info: Dict[str, Any] = {
        "request": {
            "level": request.level,
            "count": request.count,
            "target_count": target_count,
            "topic": request.topic,
            "source_ids": request.source_ids,
        },
        "retrieval": {
            "citations_count": citations_count,
            "elapsed_ms": round(t_retrieval_ms, 1),
        },
        "generation": {
            "accepted_count": accepted_count,
            "target_count": target_count,
            "rejected_count": len(rejected_items),
            "attempts": attempts,
            "elapsed_ms": round(t_llm_ms, 1),
        },
        "total": {
            "elapsed_ms": round(t_total_ms, 1),
        },
    }
    
    # retrieval側のデバッグ情報があれば追加
    if quiz_debug_info:
        debug_info["retrieval"].update(quiz_debug_info)
    
    # エラー情報があれば追加
    if error_info:
        debug_info["error"] = error_info
    
    # 試行エラーがあれば追加
    if attempt_errors:
        debug_info["attempt_errors"] = attempt_errors
    
    # バリデーション失敗アイテムがあれば追加
    if rejected_items:
        debug_info["rejected_items"] = rejected_items[:10]  # 最大10件まで
    
    # 集計統計情報を追加
    if aggregated_stats:
        debug_info["stats"] = aggregated_stats
    
    return debug_info
