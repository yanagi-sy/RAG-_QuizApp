"""
Quiz APIルーター
"""
import asyncio
import logging
import random
import time
from typing import Dict
from fastapi import APIRouter

from app.quiz.store import QuizItem, save_quiz
from app.schemas.quiz import (
    QuizRequest,
    QuizResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
)
from app.schemas.common import Citation
from app.core.settings import settings
from app.quiz.retrieval import retrieve_for_quiz
from app.quiz.generator import generate_and_validate_quizzes
from app.llm.base import LLMTimeoutError, LLMInternalError

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
    
    # クイズ専用の候補取得（サンプリング方式、タイミング計測付き）
    t_retrieval_start = time.perf_counter()
    citations, quiz_debug_info = retrieve_for_quiz(
        source_ids=request.source_ids,
        level=request.level,
        count=request.count,
        debug=request.debug
    )
    t_retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
    
    # 引用が0件の場合はエラーを返す
    if len(citations) == 0:
        return _build_error_response(
            request, quiz_debug_info,
            "引用が見つかりませんでした"
        )
    
    # MVP: 生成数を常に3問に固定（タイムアウト対策）
    target_count = min(request.count, 3)
    logger.info(f"Quiz生成目標: target={target_count}（MVP固定、req.count={request.count}）, citations={len(citations)}件")
    
    # LLMでクイズを生成（バリデーション付き）
    t_llm_start = time.perf_counter()
    accepted_quizzes, rejected_items, error_info, attempts, attempt_errors, aggregated_stats = await _generate_quizzes_with_retry(
        request, target_count, citations
    )
    t_llm_ms = (time.perf_counter() - t_llm_start) * 1000
    
    # 全体のタイミング計測
    t_total_ms = (time.perf_counter() - t_start) * 1000
    
    # debugレスポンスを構築
    final_debug = _build_debug_response(
        request, quiz_debug_info, target_count,
        len(citations), len(accepted_quizzes), rejected_items, error_info, attempts,
        attempt_errors, aggregated_stats, t_retrieval_ms, t_llm_ms, t_total_ms
    )
    
    return QuizGenerateResponse(
        quizzes=accepted_quizzes,
        debug=final_debug,
    )


async def _call_llm_and_collect(
    level: str,
    need: int,
    topic: str | None,
    citations: list[Citation],
    shuffle: bool = True
) -> tuple[list, list[dict], list[dict], dict]:
    """
    LLMでクイズを生成・パース・バリデーション（1回分）
    
    多様性確保のため、試行ごとに citations の順序をシャッフルする。
    
    Args:
        level: 難易度
        need: 生成希望件数
        topic: トピック
        citations: 引用リスト
        shuffle: citations をシャッフルするか（デフォルト: True）
        
    Returns:
        (accepted_quizzes, rejected_items, attempt_errors, generation_stats)
        - generation_stats: 生成統計（generated_true_count, generated_false_count, dropped_reasons）
    """
    # 多様性のために citations をシャッフル
    shuffled_citations = list(citations)
    if shuffle and len(shuffled_citations) > 1:
        random.shuffle(shuffled_citations)
    
    quizzes, rejected, attempt_errors, generation_stats = await generate_and_validate_quizzes(
        level=level,
        count=need,
        topic=topic,
        citations=shuffled_citations,
    )
    return (quizzes, rejected, attempt_errors, generation_stats)


async def _generate_quizzes_with_retry(
    request: QuizGenerateRequest,
    target_count: int,
    citations: list[Citation]
) -> tuple[list, list[dict], dict, int, list[dict], dict]:
    """
    クイズを生成（再試行付き、重複排除）
    
    高速化のため、quiz_max_attempts（デフォルト1回）まで試行する。
    statement の重複は排除する。
    
    Args:
        request: クイズ生成リクエスト
        target_count: 生成目標件数（request.count）
        citations: 引用リスト
        
    Returns:
        (accepted_quizzes, rejected_items, error_info, attempts, all_attempt_errors, aggregated_stats)
        - error_info: {"llm_error": str | None, "parse_error": str | None}（最終失敗時のみ）
        - all_attempt_errors: 全試行の失敗履歴（途中失敗を含む）
        - aggregated_stats: 全試行の統計集計（generated_true_count, generated_false_count, dropped_reasons）
    """
    target = target_count
    accepted_quizzes = []
    rejected_items = []
    error_info = {"llm_error": None, "parse_error": None}
    attempts = 0
    all_attempt_errors = []
    aggregated_stats = {
        "generated_true_count": 0,
        "generated_false_count": 0,
        "dropped_reasons": {},
    }  # 全試行の統計集計
    
    # statement 重複排除用のセット
    seen_statements = set()
    
    # 最大 quiz_max_attempts 回まで試行（短い出力で確実に返す戦略）
    max_attempts = settings.quiz_max_attempts
    target_per_attempt = settings.quiz_target_per_attempt  # 1回の生成で狙う問題数（3問）
    
    while len(accepted_quizzes) < target and attempts < max_attempts:
        attempts += 1
        need = target - len(accepted_quizzes)
        
        # 短い出力で確実に返す戦略: 1回あたり3問を狙う
        request_count = min(need, target_per_attempt)
        
        logger.info(
            f"Quiz生成{attempts}回目: need={need}, request_count={request_count}, "
            f"current_accepted={len(accepted_quizzes)}/{target}"
        )
        
        try:
            quizzes, rejected, attempt_errors, generation_stats = await _call_llm_and_collect(
                level=request.level,
                need=request_count,
                topic=request.topic,
                citations=citations,
            )
            
            # attempt_errors を統合（retry回数を調整）
            for err in attempt_errors:
                err["retry"] = attempts
                all_attempt_errors.append(err)
            
            # generation_stats を集計
            aggregated_stats["generated_true_count"] += generation_stats.get("generated_true_count", 0)
            aggregated_stats["generated_false_count"] += generation_stats.get("generated_false_count", 0)
            
            # dropped_reasons を集計（reason -> count）
            for reason, count in generation_stats.get("dropped_reasons", {}).items():
                aggregated_stats["dropped_reasons"][reason] = aggregated_stats["dropped_reasons"].get(reason, 0) + count
            
            # プロンプト統計とLLMパラメータを集計（最初の試行の値を保持、毎回同じはず）
            if attempts == 1:
                for key in ["llm_prompt_chars", "llm_prompt_preview_head", 
                           "llm_input_citations_count", "llm_input_total_quote_chars",
                           "llm_num_predict", "llm_temperature", "llm_timeout_sec"]:
                    if key in generation_stats:
                        aggregated_stats[key] = generation_stats[key]
            
            # LLM生出力は最新の試行の値を使用（最後に成功した出力を見たい）
            for key in ["llm_output_chars", "llm_output_preview_head"]:
                if key in generation_stats:
                    aggregated_stats[key] = generation_stats[key]
            
            # statement 重複排除
            unique_quizzes = []
            for quiz in quizzes:
                stmt = quiz.statement.strip()
                if stmt not in seen_statements:
                    seen_statements.add(stmt)
                    unique_quizzes.append(quiz)
                    
                    # 目標数に達したら打ち切り（余分な生成分を除外）
                    if len(accepted_quizzes) + len(unique_quizzes) >= target:
                        break
                else:
                    # 重複は rejected に追加
                    rejected_items.append({
                        "statement": stmt[:100],
                        "reason": "statement重複",
                    })
            
            accepted_quizzes.extend(unique_quizzes)
            rejected_items.extend(rejected)
            
            logger.info(
                f"Quiz生成{attempts}回目完了: generated={len(quizzes) + len(rejected)}, "
                f"unique_accepted={len(unique_quizzes)}, rejected={len(rejected)}, "
                f"duplicates={len(quizzes) - len(unique_quizzes)}"
            )
            
            # 生成数が0の場合は再試行しても意味がないので抜ける
            if len(quizzes) == 0:
                logger.warning("生成数が0なので試行を中断します")
                break
            
        except LLMTimeoutError as e:
            # LLMタイムアウト
            logger.error(f"Quiz生成{attempts}回目にタイムアウト: {e}")
            
            # 最終失敗時のみ error_info に記録
            if attempts >= max_attempts and not error_info["llm_error"]:
                error_info["llm_error"] = "timeout"
            
            # attempt_errors に記録
            all_attempt_errors.append({
                "retry": attempts,
                "attempt": 1,
                "stage": "llm",
                "type": "timeout",
                "message": str(e),
            })
            
            if attempts >= max_attempts:
                break
        
        except LLMInternalError as e:
            # LLM内部エラー
            logger.error(f"Quiz生成{attempts}回目にLLMエラー: {e}")
            
            # 最終失敗時のみ error_info に記録
            if attempts >= max_attempts and not error_info["llm_error"]:
                error_info["llm_error"] = f"llm_internal_error:{str(e)}"
            
            # attempt_errors に記録
            all_attempt_errors.append({
                "retry": attempts,
                "attempt": 1,
                "stage": "llm",
                "type": "llm_internal_error" if "empty_response" not in str(e) else "empty_response",
                "message": str(e),
            })
            
            if attempts >= max_attempts:
                break
        
        except ValueError as e:
            # JSONパースエラー、空応答、バリデーションエラーなど
            error_str = str(e)
            logger.error(f"Quiz生成{attempts}回目にパースエラー: {error_str}")
            
            # 最終失敗時のみ error_info に記録
            if attempts >= max_attempts:
                if "empty_response" in error_str and not error_info["llm_error"]:
                    error_info["llm_error"] = "empty_response"
                elif ("json_parse_error" in error_str or "json_validation_error" in error_str) and not error_info["parse_error"]:
                    error_info["parse_error"] = error_str
                elif "generated_zero_quizzes" in error_str and not error_info["parse_error"]:
                    error_info["parse_error"] = "generated_zero_quizzes"
                elif not error_info["parse_error"]:
                    error_info["parse_error"] = error_str
            
            # attempt_errors に記録
            all_attempt_errors.append({
                "retry": attempts,
                "attempt": 1,
                "stage": "parse" if "parse" in error_str else "validate",
                "type": "json_parse_error" if "json_parse_error" in error_str else "json_validation_error" if "json_validation_error" in error_str else "generated_zero_quizzes" if "generated_zero_quizzes" in error_str else "empty_response" if "empty_response" in error_str else "unknown",
                "message": error_str,
            })
            
            if attempts >= max_attempts:
                break
        
        except Exception as e:
            # その他の予期しないエラー
            logger.error(f"Quiz生成{attempts}回目に予期しないエラー: {type(e).__name__}: {e}")
            
            # 最終失敗時のみ error_info に記録
            if attempts >= max_attempts and not error_info["llm_error"]:
                error_info["llm_error"] = f"unexpected:{type(e).__name__}:{str(e)}"
            
            # attempt_errors に記録
            all_attempt_errors.append({
                "retry": attempts,
                "attempt": 1,
                "stage": "unknown",
                "type": "unexpected_error",
                "message": f"{type(e).__name__}: {str(e)}",
            })
            
            if attempts >= max_attempts:
                break
    
    return (accepted_quizzes, rejected_items, error_info, attempts, all_attempt_errors, aggregated_stats)


def _build_error_response(
    request: QuizGenerateRequest,
    quiz_debug_info: dict | None,
    error_message: str
) -> QuizGenerateResponse:
    """
    エラーレスポンスを構築
    """
    final_debug = None
    if request.debug:
        final_debug = quiz_debug_info or {}
        final_debug["request_source_ids"] = request.source_ids
        final_debug["request_level"] = request.level
        final_debug["request_count"] = request.count
        final_debug["error"] = error_message
    
    return QuizGenerateResponse(
        quizzes=[],
        debug=final_debug,
    )


def _build_debug_response(
    request: QuizGenerateRequest,
    quiz_debug_info: dict | None,
    target_count: int,
    citations_count: int,
    accepted_count: int,
    rejected_items: list[dict],
    error_info: dict,
    attempts: int,
    attempt_errors: list[dict],
    aggregated_stats: dict,
    t_retrieval_ms: float,
    t_llm_ms: float,
    t_total_ms: float
) -> dict | None:
    """
    debugレスポンスを構築（timing情報、attempt_errors、generation_stats付き）
    """
    if not request.debug:
        return None
    
    final_debug = quiz_debug_info or {}
    
    # リクエスト情報を追加
    final_debug["request_source_ids"] = request.source_ids
    final_debug["request_level"] = request.level
    final_debug["request_count"] = request.count
    final_debug["request_topic"] = request.topic
    final_debug["target_count"] = target_count
    final_debug["citations_count"] = citations_count
    final_debug["quiz_generation_attempts"] = attempts
    final_debug["generated_count"] = accepted_count + len(rejected_items)
    final_debug["accepted_count"] = accepted_count
    final_debug["rejected_count"] = len(rejected_items)
    final_debug["quiz_shortfall"] = target_count - accepted_count
    
    # 生成統計を追加（値がある時だけセット、0初期化しない）
    if "generated_true_count" in aggregated_stats:
        final_debug["generated_true_count"] = aggregated_stats["generated_true_count"]
    if "generated_false_count" in aggregated_stats:
        final_debug["generated_false_count"] = aggregated_stats["generated_false_count"]
    if "dropped_reasons" in aggregated_stats:
        final_debug["dropped_reasons"] = aggregated_stats["dropped_reasons"]
    
    # LLM負担計測（プロンプト統計、値がある時だけセット）
    if "llm_prompt_chars" in aggregated_stats:
        final_debug["llm_prompt_chars"] = aggregated_stats["llm_prompt_chars"]
    if "llm_prompt_preview_head" in aggregated_stats:
        final_debug["llm_prompt_preview_head"] = aggregated_stats["llm_prompt_preview_head"]
    if "llm_input_citations_count" in aggregated_stats:
        final_debug["llm_input_citations_count"] = aggregated_stats["llm_input_citations_count"]
    if "llm_input_total_quote_chars" in aggregated_stats:
        final_debug["llm_input_total_quote_chars"] = aggregated_stats["llm_input_total_quote_chars"]
    
    # LLM生出力計測（値がある時だけセット）
    if "llm_output_chars" in aggregated_stats:
        final_debug["llm_output_chars"] = aggregated_stats["llm_output_chars"]
    if "llm_output_preview_head" in aggregated_stats:
        final_debug["llm_output_preview_head"] = aggregated_stats["llm_output_preview_head"]
    
    # LLMパラメータ（値がある時だけセット）
    if "llm_num_predict" in aggregated_stats:
        final_debug["llm_num_predict"] = aggregated_stats["llm_num_predict"]
    if "llm_temperature" in aggregated_stats:
        final_debug["llm_temperature"] = aggregated_stats["llm_temperature"]
    if "llm_timeout_sec" in aggregated_stats:
        final_debug["llm_timeout_sec"] = aggregated_stats["llm_timeout_sec"]
    
    # LLM試行回数
    final_debug["llm_attempts"] = attempts  # 生成試行回数
    final_debug["llm_retries"] = max(0, attempts - 1)  # 再試行回数（初回除く）
    
    # タイミング情報を追加（ms単位、小数点1桁）
    final_debug["timing"] = {
        "retrieval": round(t_retrieval_ms, 1),
        "llm": round(t_llm_ms, 1),
        "total": round(t_total_ms, 1),
    }
    
    # rejected_reasons を集計
    rejected_reasons: Dict[str, int] = {}
    for item in rejected_items:
        reason = item.get("reason", "unknown")
        rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
    final_debug["rejected_reasons"] = rejected_reasons
    
    # sample_rejected（先頭1〜2件）
    if len(rejected_items) > 0:
        final_debug["sample_rejected"] = rejected_items[:2]
    
    # エラー情報を追加（最終失敗時のみ）
    if error_info.get("llm_error"):
        final_debug["llm_error"] = error_info["llm_error"]
    if error_info.get("parse_error"):
        final_debug["parse_error"] = error_info["parse_error"]
    
    # attempt_errors を追加（途中失敗を含む）
    final_debug["attempt_errors"] = attempt_errors
    
    return final_debug
