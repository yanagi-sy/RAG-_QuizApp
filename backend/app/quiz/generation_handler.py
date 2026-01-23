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


def _get_core_content_key(statement: str) -> str:
    """
    コア内容キーを取得（否定語除去後の正規化）
    
    重複判定用に、否定語（しない/行わない/禁止/不要/ではない等）を除去した
    コア内容のみで比較する。これにより「行う/行わない」の単純反転が
    同一セットに混入しないようにする。
    
    Args:
        statement: クイズのstatement
        
    Returns:
        コア内容キー（否定語除去後の正規化）
    """
    # 否定語パターン（優先度順）
    negation_patterns = [
        r'しない',
        r'行わない',
        r'ではない',
        r'なくてもよい',
        r'禁止',
        r'不要',
        r'してはいけない',
        r'行ってはいけない',
        r'してはならない',
        r'行ってはならない',
    ]
    
    # 否定語を除去
    core = statement
    for pattern in negation_patterns:
        core = re.sub(pattern, '', core)
    
    # 正規化（空白除去、句読点除去、小文字化）
    normalized = re.sub(r'\s+', '', core)
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    return normalized.lower()


def _is_duplicate(new_statement: str, existing_statements: list[str]) -> bool:
    """
    新しいstatementが既存のものと重複しているかチェック
    
    重複判定は2段階で行う:
    1. 通常の正規化（空白・句読点除去）で完全一致チェック
    2. コア内容キー（否定語除去後）で一致チェック（「行う/行わない」の単純反転を検出）
    
    Args:
        new_statement: 新しいstatement
        existing_statements: 既存のstatementリスト
        
    Returns:
        True: 重複している、False: 重複していない
    """
    # 1. 通常の正規化で完全一致チェック
    normalized_new = _normalize_statement(new_statement)
    for existing in existing_statements:
        normalized_existing = _normalize_statement(existing)
        if normalized_new == normalized_existing:
            logger.info(f"重複検出（完全一致）: '{new_statement[:50]}...' と '{existing[:50]}...' が重複しています")
            return True
    
    # 2. コア内容キー（否定語除去後）で一致チェック
    core_key_new = _get_core_content_key(new_statement)
    for existing in existing_statements:
        core_key_existing = _get_core_content_key(existing)
        if core_key_new == core_key_existing and core_key_new:  # 空文字列は除外
            logger.info(f"重複検出（コア内容一致）: '{new_statement[:50]}...' と '{existing[:50]}...' がコア内容で重複しています")
            return True
    
    return False


def _is_citation_duplicate(quiz_citations: list[Citation], used_citation_keys: set) -> bool:
    """
    クイズのcitationsが既に使用済みかチェック
    
    Args:
        quiz_citations: クイズのcitationsリスト
        used_citation_keys: 使用済みcitationキーのセット
        
    Returns:
        True: 重複している（既に使用済みのcitationを含む）、False: 重複していない
    """
    for citation in quiz_citations:
        citation_key = (
            citation.source,
            citation.page,
            citation.quote[:60] if citation.quote else ""
        )
        if citation_key in used_citation_keys:
            # TypeError対策: pageを文字列に変換
            page_str = str(citation.page) if citation.page is not None else "None"
            logger.info(
                f"出題箇所重複検出: '{citation.source}' (p.{page_str}) は既に使用済みです"
            )
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
    
    【新戦略】出題箇所（citation）ごとに正誤ペアを生成し、確率的に片方を採用
    - 1つのcitationから正誤ペア（○と×）を必ず生成
    - 各ペアから確率的に片方（○または×）を選択（デフォルト50%ずつ）
    - これにより出題箇所の重複を完全に防ぐ
    
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
    import random
    
    # CHANGED: 新戦略では、citationごとにペアを生成するため、試行回数の計算を変更
    # 1回の試行で5つのcitationから5ペア（計10問）を生成し、その中から目標数分を選択
    # 目標数に達するまで、複数回試行する
    base_max_attempts = settings.quiz_max_attempts
    # 目標数÷5（1回の試行で5ペア生成） + 余裕を持たせる
    calculated_max_attempts = max(base_max_attempts, (target_count // 5) + 2)
    max_attempts = calculated_max_attempts
    
    # 確率的選択の設定（○と×の選択確率、デフォルトは50%ずつ）
    true_probability = 0.5  # ○を選択する確率（50%）
    
    accepted_quizzes = []
    all_rejected_items = []
    all_attempt_errors = []
    aggregated_stats = {}
    
    # 重複チェック用: 既に採用されたstatementのリスト
    accepted_statements = []
    
    # 目標数に達するまで、または最大試行回数に達するまで繰り返す
    attempts = 0
    
    # 重複対策: 使用済みcitationsを記録（同じcitationから同じクイズが生成されるのを防ぐ）
    # 【新戦略】1つのcitationから1ペアのみ生成するため、citationの重複は発生しない
    used_citation_keys = set()
    
    # banned_statements: 既出・重複で落としたstatementを保持（retry時にLLMに渡す）
    banned_statements = []
    banned_statements_max = 30  # 上限（長くなりすぎないように）
    
    logger.info(
        f"[GENERATION_RETRY] 開始: target={target_count}, max_attempts={max_attempts} "
        f"(base={base_max_attempts}, calculated={calculated_max_attempts}), "
        f"strategy=ペア生成方式（citationごとに正誤ペア生成→確率的選択）"
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
            # 使用済みcitationsを除外したcitationsを取得
            available_citations = [
                c for c in citations
                if (c.source, c.page, c.quote[:60] if c.quote else "") not in used_citation_keys
            ]
            
            # 使用可能なcitationsが少ない場合は、使用済みをリセット
            if len(available_citations) < 5:
                logger.info(
                    f"[GENERATION_RETRY] 使用済みリストをリセット "
                    f"(available={len(available_citations)}, accepted={len(accepted_quizzes)})"
                )
                used_citation_keys.clear()
                available_citations = citations
            
            # 使用可能なcitationsから5件を選択（1回の試行で5ペア生成）
            if len(available_citations) >= 5:
                selected_citations_list = random.sample(available_citations, 5)
            else:
                selected_citations_list = available_citations[:5] if len(available_citations) > 0 else []
            
            if len(selected_citations_list) == 0:
                logger.warning("[GENERATION_RETRY] 使用可能なcitationsがありません")
                break
            
            # 【新戦略】各citationから正誤ペアを生成
            batch_pairs = []  # (true_quiz, false_quiz, single_citation) のタプルリスト
            batch_rejected = []
            batch_attempt_errors = []
            batch_stats = {}
            
            for citation_idx, single_citation in enumerate(selected_citations_list):
                # debugログ: selected_citationを出力
                logger.info(
                    f"[GENERATION:SELECTED_CITATION] citation_idx={citation_idx}, "
                    f"source={single_citation.source}, page={single_citation.page}, "
                    f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                )
                
                # 1つのcitationから正誤ペアを生成
                pair_accepted, pair_rejected, pair_attempt_errors, pair_stats = await generate_and_validate_quizzes(
                    level=request.level,
                    count=1,  # 1問ずつ生成（○と×のペアが返される）
                    topic=request.topic,
                    citations=[single_citation],  # 1つのcitationのみを使用
                    request_id=request_id,
                    attempt_index=f"{attempts}-{citation_idx}",
                    banned_statements=banned_statements if len(banned_statements) > 0 else None,
                )
                
                # 統計情報をマージ
                for key, value in pair_stats.items():
                    if key in batch_stats:
                        if isinstance(value, (int, float)):
                            batch_stats[key] += value
                        elif isinstance(value, dict):
                            for k, v in value.items():
                                prev = batch_stats[key].get(k)
                                if isinstance(v, (int, float)) and isinstance(prev, (int, float)):
                                    batch_stats[key][k] = prev + v
                                else:
                                    batch_stats[key][k] = v
                    else:
                        batch_stats[key] = value
                
                batch_rejected.extend(pair_rejected)
                batch_attempt_errors.extend(pair_attempt_errors)
                
                # ○と×を分ける
                pair_true = [q for q in pair_accepted if q.answer_bool]
                pair_false = [q for q in pair_accepted if not q.answer_bool]
                
                # ペアが揃っている場合のみ採用（single_citationも一緒に保持）
                if len(pair_true) > 0 and len(pair_false) > 0:
                    batch_pairs.append((pair_true[0], pair_false[0], single_citation))
                    logger.info(
                        f"[GENERATION_RETRY] citation {citation_idx+1}/5: ペア生成成功 "
                        f"(○: '{pair_true[0].statement[:40]}...', ×: '{pair_false[0].statement[:40]}...')"
                    )
                else:
                    logger.warning(
                        f"[GENERATION_RETRY] citation {citation_idx+1}/5: ペア生成失敗 "
                        f"(○={len(pair_true)}, ×={len(pair_false)})"
                    )
            
            # 各ペアから確率的に片方を選択
            new_accepted_quizzes = []
            for pair_idx, (true_quiz, false_quiz, single_citation) in enumerate(batch_pairs):
                # single_citationはタプルから直接取得（対応関係が保証される）
                corresponding_citation = single_citation
                
                # 確率的に○または×を選択
                selected_quiz = random.choices(
                    [true_quiz, false_quiz],
                    weights=[true_probability, 1 - true_probability]
                )[0]
                
                # statementの重複チェック（念のため）
                if _is_duplicate(selected_quiz.statement, accepted_statements):
                    logger.warning(f"重複クイズを除外: '{selected_quiz.statement[:50]}...'")
                    all_rejected_items.append({
                        "statement": selected_quiz.statement[:100],
                        "reason": "duplicate_statement",
                    })
                    continue
                
                # 【重要】citationsを必ず付与（LLM出力に依存しない）
                # selected_quizのcitationsが空または不十分な場合、single_citationを必ず付与
                if not selected_quiz.citations or len(selected_quiz.citations) == 0:
                    if corresponding_citation:
                        # Pydanticモデルを更新（model_copyを使用）
                        selected_quiz = selected_quiz.model_copy(update={"citations": [corresponding_citation]})
                        logger.info(
                            f"[GENERATION:CITATION_ASSIGNED] quizにcitationsがなかったため、selected_citationを付与: "
                            f"source={corresponding_citation.source}, page={corresponding_citation.page}"
                        )
                    else:
                        logger.warning(f"[GENERATION:CITATION_MISSING] 対応するcitationが見つかりません（pair_idx={pair_idx}）")
                
                # citationsが既にある場合でも、selected_citationが含まれているか確認
                # 含まれていない場合は、selected_citationを先頭に追加（確実に紐付け）
                if corresponding_citation:
                    citation_sources = [c.source for c in selected_quiz.citations]
                    if corresponding_citation.source not in citation_sources:
                        # selected_citationを先頭に追加
                        updated_citations = [corresponding_citation] + selected_quiz.citations
                        selected_quiz = selected_quiz.model_copy(update={"citations": updated_citations})
                        logger.info(
                            f"[GENERATION:CITATION_PREPENDED] selected_citationを先頭に追加: "
                            f"source={corresponding_citation.source}, page={corresponding_citation.page}, "
                            f"final_citations_count={len(updated_citations)}"
                        )
                    else:
                        logger.info(
                            f"[GENERATION:CITATION_VERIFIED] selected_citationが既に含まれています: "
                            f"source={corresponding_citation.source}, final_citations_count={len(selected_quiz.citations)}"
                        )
                
                # 採用
                new_accepted_quizzes.append(selected_quiz)
                accepted_statements.append(selected_quiz.statement)
                
                # debugログ: selected_citationとfinal_citations_countを出力
                final_citations_count = len(selected_quiz.citations)
                selected_citation_info = f"{corresponding_citation.source}(p.{corresponding_citation.page})" if corresponding_citation else "NONE"
                logger.info(
                    f"[GENERATION:DEBUG] selected_citation={selected_citation_info}, "
                    f"final_citations_count={final_citations_count}, "
                    f"quiz_statement_preview={selected_quiz.statement[:50]}"
                )
                
                # 使用済みcitationsを記録（このcitationは使用済みとしてマーク）
                # ペアの両方のcitationsを記録（○と×は同じcitationを使用）
                for citation in true_quiz.citations:
                    citation_key = (
                        citation.source,
                        citation.page,
                        citation.quote[:60] if citation.quote else ""
                    )
                    used_citation_keys.add(citation_key)
            
            # 結果を集計
            accepted_quizzes.extend(new_accepted_quizzes)
            all_rejected_items.extend(batch_rejected)
            all_attempt_errors.extend(batch_attempt_errors)
            
            logger.info(
                f"[GENERATION_RETRY] attempt={attempts} 完了: "
                f"pairs_generated={len(batch_pairs)}, selected={len(new_accepted_quizzes)}, "
                f"rejected={len(batch_rejected)}, total_accepted={len(accepted_quizzes)}"
            )
            
            # 統計情報をマージ
            for key, value in batch_stats.items():
                if key in aggregated_stats:
                    if isinstance(value, (int, float)):
                        aggregated_stats[key] += value
                    elif isinstance(value, dict):
                        for k, v in value.items():
                            prev = aggregated_stats[key].get(k)
                            if isinstance(v, (int, float)) and isinstance(prev, (int, float)):
                                aggregated_stats[key][k] = prev + v
                            else:
                                aggregated_stats[key][k] = v
                else:
                    aggregated_stats[key] = value
            
            
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
    
    # 【新戦略】確率的選択により既にバランスが取れているため、そのまま使用
    # ただし、目標数を超えている場合はスライス
    if len(accepted_quizzes) > target_count:
        logger.info(f"生成数が目標数（{target_count}問）を超えています（{len(accepted_quizzes)}問）。目標数にスライスします。")
        accepted_quizzes = accepted_quizzes[:target_count]
    
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
