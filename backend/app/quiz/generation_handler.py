"""
Quiz生成の再試行ロジック

generate_and_validate_quizzes を呼び出して、複数回試行する。
"""
import logging
import re
from typing import Dict, Any

from app.schemas.quiz import QuizGenerateRequest, QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.quiz.generator import generate_and_validate_quizzes
from app.core.settings import settings

# ロガー設定
logger = logging.getLogger(__name__)


def _normalize_statement(statement: str) -> str:
    """
    statementを正規化して比較用に使用
    
    Args:
        statement: クイズのstatement
        
    Returns:
        正規化されたstatement（空白除去、句読点統一、小文字化）
    """
    # 空白を除去
    normalized = re.sub(r'\s+', '', statement)
    # 句読点を統一（句読点を除去）
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    return normalized.lower()


def _is_duplicate(new_statement: str, existing_statements: list[str]) -> bool:
    """
    新しいstatementが既存のものと重複しているかチェック
    
    Args:
        new_statement: 新しいstatement
        existing_statements: 既存のstatementリスト
        
    Returns:
        True: 重複している、False: 重複していない
    """
    normalized_new = _normalize_statement(new_statement)
    for existing in existing_statements:
        normalized_existing = _normalize_statement(existing)
        if normalized_new == normalized_existing:
            logger.info(f"重複検出: '{new_statement[:50]}...' と '{existing[:50]}...' が重複しています")
            return True
    return False


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
    # CHANGED: 目標数に基づいて最大試行回数を動的に計算
    # 各試行で○×2件を生成するため、目標数÷2 + 余裕を持たせる
    base_max_attempts = settings.quiz_max_attempts
    # 目標数に応じて調整（最低でも目標数÷2 + 2回の余裕）
    calculated_max_attempts = max(base_max_attempts, (target_count // 2) + 2)
    max_attempts = calculated_max_attempts
    
    accepted_quizzes = []
    all_rejected_items = []
    all_attempt_errors = []
    aggregated_stats = {}
    
    # 重複チェック用: 既に採用されたstatementのリスト
    accepted_statements = []
    
    # 目標数に達するまで、または最大試行回数に達するまで繰り返す
    attempts = 0
    consecutive_duplicates = 0  # 連続重複回数（無限ループ防止）
    max_consecutive_duplicates = 10  # 最大連続重複回数
    
    # 重複対策: 使用済みcitationsを記録（同じcitationから同じクイズが生成されるのを防ぐ）
    used_citation_keys = set()
    
    logger.info(
        f"[GENERATION_RETRY] 開始: target={target_count}, max_attempts={max_attempts} "
        f"(base={base_max_attempts}, calculated={calculated_max_attempts})"
    )
    
    while len(accepted_quizzes) < target_count and attempts < max_attempts:
        attempts += 1
        
        # 残り必要数
        remaining = target_count - len(accepted_quizzes)
        
        logger.info(
            f"[GENERATION_RETRY] attempt={attempts}/{max_attempts}, "
            f"accepted={len(accepted_quizzes)}, target={target_count}, remaining={remaining}"
        )
        
        try:
            # 重複対策: 使用済みcitationsを除外したcitationsを生成に使用
            # 各試行で異なるcitationsを使うことで、多様なクイズを生成
            available_citations = [
                c for c in citations
                if (c.source, c.page, c.quote[:60] if c.quote else "") not in used_citation_keys
            ]
            
            # 使用可能なcitationsが少ない場合は、使用済みをリセット
            if len(available_citations) < 3:
                logger.info(f"[GENERATION_RETRY] 使用可能なcitationsが少ないため、使用済みリストをリセット")
                used_citation_keys.clear()
                available_citations = citations
            
            # 使用可能なcitationsからランダムに選択（多様性を確保）
            import random
            if len(available_citations) > 5:
                # 5件以上ある場合は、ランダムに5件選択
                selected_citations = random.sample(available_citations, 5)
            else:
                selected_citations = available_citations
            
            # 1問ずつ生成（generate_and_validate_quizzesはcount=1専用）
            batch_accepted, batch_rejected, batch_attempt_errors, batch_stats = await generate_and_validate_quizzes(
                level=request.level,
                count=1,  # 1問ずつ生成
                topic=request.topic,
                citations=selected_citations,  # 選択したcitationsを使用
                request_id=request_id,
                attempt_index=attempts,
            )
            
            # 重複チェック: 新しく生成されたクイズが既存のものと重複していないか確認
            # CHANGED: ○と×を別々に管理し、最終的にバランス良く配置する
            new_accepted_true = []
            new_accepted_false = []
            
            for quiz in batch_accepted:
                # 重複チェック
                if _is_duplicate(quiz.statement, accepted_statements):
                    # 重複している場合は除外
                    logger.warning(f"重複クイズを除外: '{quiz.statement[:50]}...'")
                    all_rejected_items.append({
                        "statement": quiz.statement[:100],
                        "reason": "duplicate_statement",
                    })
                    consecutive_duplicates += 1
                else:
                    # 重複していない場合は採用
                    # ○と×を分けて管理
                    if quiz.answer_bool:
                        new_accepted_true.append(quiz)
                    else:
                        new_accepted_false.append(quiz)
                    accepted_statements.append(quiz.statement)
                    consecutive_duplicates = 0  # リセット
                    
                    # 使用済みcitationsを記録（重複対策）
                    for citation in quiz.citations:
                        citation_key = (
                            citation.source,
                            citation.page,
                            citation.quote[:60] if citation.quote else ""
                        )
                        used_citation_keys.add(citation_key)
            
            # 重複が連続で発生した場合の警告
            if consecutive_duplicates >= max_consecutive_duplicates:
                logger.warning(
                    f"連続{consecutive_duplicates}回重複が発生しました。"
                    f"無限ループを防ぐため、この試行をスキップします。"
                )
                consecutive_duplicates = 0  # リセット
                continue  # この試行をスキップ
            
            # 結果を集計（重複除外後のクイズのみ）
            # CHANGED: ○と×を別々に追加（後でバランス良く配置するため）
            accepted_quizzes.extend(new_accepted_true)
            accepted_quizzes.extend(new_accepted_false)
            all_rejected_items.extend(batch_rejected)
            all_attempt_errors.extend(batch_attempt_errors)
            
            logger.info(
                f"[GENERATION_RETRY] attempt={attempts} 完了: "
                f"accepted_true={len(new_accepted_true)}, accepted_false={len(new_accepted_false)}, "
                f"rejected={len(batch_rejected)}, total_accepted={len(accepted_quizzes)}"
            )
            
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
            
            # ログは既に上で出力されているため、ここでは簡潔に
            pass
            
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
    
    # CHANGED: ○と×をバランス良く配置（交互に配置）
    # まず、○と×を分ける
    accepted_true = [q for q in accepted_quizzes if q.answer_bool]
    accepted_false = [q for q in accepted_quizzes if not q.answer_bool]
    
    # ○と×を交互に配置（バランス良く）
    balanced_quizzes = []
    max_len = max(len(accepted_true), len(accepted_false))
    for i in range(max_len):
        if i < len(accepted_true):
            balanced_quizzes.append(accepted_true[i])
        if i < len(accepted_false):
            balanced_quizzes.append(accepted_false[i])
    
    # 目標数に達するまで、または最大試行回数に達するまで繰り返す
    # ただし、目標数に達した場合はスライス
    if len(balanced_quizzes) > target_count:
        logger.info(f"生成数が目標数（{target_count}問）を超えています（{len(balanced_quizzes)}問）。目標数にスライスします。")
        balanced_quizzes = balanced_quizzes[:target_count]
    
    accepted_quizzes = balanced_quizzes
    
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
    aggregated_stats["final_true_count"] = len([q for q in accepted_quizzes if q.answer_bool])
    aggregated_stats["final_false_count"] = len([q for q in accepted_quizzes if not q.answer_bool])
    
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
