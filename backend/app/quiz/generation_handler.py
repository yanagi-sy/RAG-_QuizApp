"""
Quiz生成の再試行ロジック

generate_and_validate_quizzes を呼び出して、複数回試行する。
"""
import logging
import unicodedata
from typing import Dict, Any

from app.schemas.quiz import QuizGenerateRequest, QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.quiz.generator import generate_and_validate_quizzes
from app.quiz.duplication_checker import (
    is_duplicate_statement,
    is_citation_duplicate,
    create_citation_key,
)
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
    
    # banned_statements: 既出・重複で落としたstatementを保持（retry時にLLMに渡す）
    banned_statements = []
    banned_statements_max = 30  # 上限（長くなりすぎないように）
    
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
                if create_citation_key(c) not in used_citation_keys
            ]
            
            # 使用可能なcitationsが少ない場合、または連続重複が多すぎる場合は、使用済みをリセット
            # 重複が多すぎて規定数に達しない問題を解決するため、より積極的にリセット
            # 【改善】citationsを再取得するロジックを追加（retrieval.pyを呼び出す）
            should_reset = (
                len(available_citations) < 3 or  # 3件未満の場合（より積極的にリセット）
                consecutive_duplicates >= 3 or  # 連続3回重複した場合（より積極的にリセット）
                (attempts > 2 and len(accepted_quizzes) == 0) or  # 2回以上試行しても1件も採用されていない場合
                (attempts > 5 and len(accepted_quizzes) < target_count // 2)  # 5回以上試行しても目標数の半分に達していない場合
            )
            
            if should_reset:
                logger.info(
                    f"[GENERATION_RETRY] 使用済みリストをリセット "
                    f"(available={len(available_citations)}, consecutive_duplicates={consecutive_duplicates}, "
                    f"accepted={len(accepted_quizzes)})"
                )
                
                # 【改善】citationsを再取得（retrieval.pyを呼び出す）
                # リセットする前に、citationsを増やすことで、より多くの候補を確保
                if attempts < max_attempts - 1 and len(citations) < target_count * 2:
                    try:
                        from app.quiz.retrieval import retrieve_for_quiz
                        logger.info(
                            f"[GENERATION_RETRY] citationsを再取得 "
                            f"(current={len(citations)}, target={target_count * 2})"
                        )
                        new_citations, _ = retrieve_for_quiz(
                            source_ids=request.source_ids,
                            level=request.level,
                            count=target_count * 2,  # 多めに取得
                            debug=False
                        )
                        if len(new_citations) > 0:
                            citations = new_citations
                            logger.info(
                                f"[GENERATION_RETRY] citations再取得完了: {len(citations)}件"
                            )
                    except Exception as e:
                        logger.warning(
                            f"[GENERATION_RETRY] citations再取得失敗: {type(e).__name__}: {e}, "
                            f"既存のcitationsを使用します"
                        )
                
                used_citation_keys.clear()
                available_citations = citations
                consecutive_duplicates = 0  # リセット時に連続重複もリセット
            
            # 使用可能なcitationsから選択（多様性を確保、出題箇所の重複を避ける）
            import random
            # 【改善】出題箇所の重複を避けるため、より多様なcitationsを選択
            # 使用済みcitationsと異なるquoteを持つcitationsを優先的に選択
            if len(available_citations) > 5:
                # 使用済みcitationsのquote先頭60文字を取得
                used_quote_prefixes = {
                    quote[:60] if quote else ""
                    for _, _, quote in used_citation_keys
                }
                
                # 使用済みquoteと異なるcitationsを優先的に選択
                diverse_citations = [
                    c for c in available_citations
                    if (c.quote[:60] if c.quote else "") not in used_quote_prefixes
                ]
                
                if len(diverse_citations) >= 5:
                    # 多様なcitationsが5件以上ある場合は、そこからランダムに5件選択
                    selected_citations = random.sample(diverse_citations, 5)
                elif len(diverse_citations) > 0:
                    # 多様なcitationsが1-4件の場合は、それに加えて残りを補完
                    remaining_needed = 5 - len(diverse_citations)
                    remaining_citations = [
                        c for c in available_citations
                        if c not in diverse_citations
                    ]
                    selected_citations = diverse_citations + random.sample(
                        remaining_citations, min(remaining_needed, len(remaining_citations))
                    )
                else:
                    # 多様なcitationsがない場合は、ランダムに5件選択
                    selected_citations = random.sample(available_citations, 5)
            else:
                selected_citations = available_citations
            
            # 1問ずつ生成（generate_and_validate_quizzesはcount=1専用）
            # banned_statementsを渡して、既出・重複で落としたstatementを避ける
            batch_accepted, batch_rejected, batch_attempt_errors, batch_stats = await generate_and_validate_quizzes(
                level=request.level,
                count=1,  # 1問ずつ生成
                topic=request.topic,
                citations=selected_citations,  # 選択したcitationsを使用
                request_id=request_id,
                attempt_index=attempts,
                banned_statements=banned_statements if len(banned_statements) > 0 else None,
            )
            
            # 重複チェック: 新しく生成されたクイズが既存のものと重複していないか確認
            # CHANGED: ○と×を別々に管理し、最終的にバランス良く配置する
            # また、○と×のペアが同じcitationから生成される場合、そのcitationを1回だけカウントする
            new_accepted_true = []
            new_accepted_false = []
            
            # ○と×のペアを一緒に処理するため、まず○と×を分ける
            batch_true = [q for q in batch_accepted if q.answer_bool]
            batch_false = [q for q in batch_accepted if not q.answer_bool]
            
            # ○と×のペアを一緒に処理（同じcitationから生成されたペアは1つのcitationとして扱う）
            # まず、○と×のペアをマッチング（同じcitationから生成された可能性が高い）
            processed_true_quizzes = []
            processed_false_quizzes = []
            
            # 【品質担保】指定sourceを取得（source不一致チェック用）
            expected_source = None
            if request.source_ids and len(request.source_ids) > 0:
                expected_source = unicodedata.normalize("NFC", request.source_ids[0])
            
            # ○を処理
            for true_quiz in batch_true:
                # 【品質担保】citationのsourceが指定ソースと一致することを確認
                if expected_source and true_quiz.citations:
                    for citation in true_quiz.citations:
                        citation_source_norm = unicodedata.normalize("NFC", citation.source)
                        if citation_source_norm != expected_source:
                            logger.error(
                                f"[GENERATION:SOURCE_MISMATCH] 【重大】citationのsourceが不一致: "
                                f"expected={expected_source}, actual={citation.source} (norm={citation_source_norm}), "
                                f"quiz_statement={true_quiz.statement[:50]}"
                            )
                            all_rejected_items.append({
                                "statement": true_quiz.statement[:100],
                                "reason": "source_mismatch",
                                "expected_source": expected_source,
                                "actual_source": citation.source,
                            })
                            consecutive_duplicates += 1
                            # このクイズをスキップ（エラーとして扱う）
                            continue
                
                # 重複チェック1: statementの重複
                if is_duplicate_statement(true_quiz.statement, accepted_statements):
                    logger.warning(f"重複クイズを除外: '{true_quiz.statement[:50]}...'")
                    all_rejected_items.append({
                        "statement": true_quiz.statement[:100],
                        "reason": "duplicate_statement",
                    })
                    # banned_statementsに追加（上限チェック）
                    if len(banned_statements) < banned_statements_max:
                        banned_statements.append(true_quiz.statement)
                    consecutive_duplicates += 1
                    continue
                
                # 重複チェック2: citationの重複（出題箇所の重複）
                if is_citation_duplicate(true_quiz.citations, used_citation_keys):
                    # TypeError対策: pageを文字列に変換
                    citation_strs = [
                        f"{c.source}(p.{c.page})" if c.page is not None else f"{c.source}(p.None)"
                        for c in true_quiz.citations[:2]
                    ]
                    logger.warning(
                        f"出題箇所重複クイズを除外: '{true_quiz.statement[:50]}...' "
                        f"(citations: {citation_strs})"
                    )
                    all_rejected_items.append({
                        "statement": true_quiz.statement[:100],
                        "reason": "duplicate_citation",
                    })
                    # banned_statementsに追加（上限チェック）
                    if len(banned_statements) < banned_statements_max:
                        banned_statements.append(true_quiz.statement)
                    consecutive_duplicates += 1
                    continue
                
                # ○を採用候補に追加
                processed_true_quizzes.append(true_quiz)
            
            # ×を処理（○から生成された×は、対応する○と同じcitationを使用している可能性が高い）
            # 対応する○が採用された場合、×も同じcitationを使用していても採用する
            for false_quiz in batch_false:
                # 【品質担保】citationのsourceが指定ソースと一致することを確認
                if expected_source and false_quiz.citations:
                    for citation in false_quiz.citations:
                        citation_source_norm = unicodedata.normalize("NFC", citation.source)
                        if citation_source_norm != expected_source:
                            logger.error(
                                f"[GENERATION:SOURCE_MISMATCH] 【重大】citationのsourceが不一致（×）: "
                                f"expected={expected_source}, actual={citation.source} (norm={citation_source_norm}), "
                                f"quiz_statement={false_quiz.statement[:50]}"
                            )
                            all_rejected_items.append({
                                "statement": false_quiz.statement[:100],
                                "reason": "source_mismatch",
                                "expected_source": expected_source,
                                "actual_source": citation.source,
                            })
                            consecutive_duplicates += 1
                            # このクイズをスキップ（エラーとして扱う）
                            continue
                
                # 重複チェック1: statementの重複
                if is_duplicate_statement(false_quiz.statement, accepted_statements):
                    logger.warning(f"重複クイズを除外: '{false_quiz.statement[:50]}...'")
                    all_rejected_items.append({
                        "statement": false_quiz.statement[:100],
                        "reason": "duplicate_statement",
                    })
                    # banned_statementsに追加（上限チェック）
                    if len(banned_statements) < banned_statements_max:
                        banned_statements.append(false_quiz.statement)
                    consecutive_duplicates += 1
                    continue
                
                # 重複チェック2: citationの重複（出題箇所の重複）
                # 注意: ×は○から生成されるため、同じcitationを使用している可能性が高い
                # しかし、対応する○が採用された場合、×も採用する（○と×のペアは1つのcitationとして扱う）
                # ただし、他の○問題と同じcitationを使用している場合は除外する
                if is_citation_duplicate(false_quiz.citations, used_citation_keys):
                    # 対応する○が採用候補にあるかチェック（同じcitationを使用している可能性）
                    has_corresponding_true = any(
                        any(
                            create_citation_key(c1) == create_citation_key(c2)
                            for c1 in false_quiz.citations
                            for c2 in true_quiz.citations
                        )
                        for true_quiz in processed_true_quizzes
                    )
                    
                    if not has_corresponding_true:
                        # 対応する○がない場合、出題箇所の重複として除外
                        citation_strs = [
                            f"{c.source}(p.{c.page})" if c.page is not None else f"{c.source}(p.None)"
                            for c in false_quiz.citations[:2]
                        ]
                        logger.warning(
                            f"出題箇所重複クイズを除外: '{false_quiz.statement[:50]}...' "
                            f"(citations: {citation_strs})"
                        )
                    all_rejected_items.append({
                        "statement": false_quiz.statement[:100],
                        "reason": "duplicate_citation",
                    })
                    # banned_statementsに追加（上限チェック）
                    if len(banned_statements) < banned_statements_max:
                        banned_statements.append(false_quiz.statement)
                    consecutive_duplicates += 1
                    continue
                    # 対応する○がある場合、×も採用する（○と×のペアは1つのcitationとして扱う）
                
                # ×を採用候補に追加
                processed_false_quizzes.append(false_quiz)
            
            # 採用候補を実際に採用
            for true_quiz in processed_true_quizzes:
                new_accepted_true.append(true_quiz)
                accepted_statements.append(true_quiz.statement)
                consecutive_duplicates = 0  # リセット
                
                # 使用済みcitationsを記録（○のcitationsを記録）
                for citation in true_quiz.citations:
                    citation_key = create_citation_key(citation)
                    used_citation_keys.add(citation_key)
            
            for false_quiz in processed_false_quizzes:
                new_accepted_false.append(false_quiz)
                accepted_statements.append(false_quiz.statement)
                consecutive_duplicates = 0  # リセット
                
                # 使用済みcitationsを記録（×のcitationsも記録）
                # 注意: ×は○から生成されるため、同じcitationを使用している可能性が高い
                # その場合、既に使用済みになっているが、念のため記録する
                for citation in false_quiz.citations:
                    citation_key = create_citation_key(citation)
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
                        # dictの場合はマージ（数値のみ加算、それ以外は上書き）
                        # sample_mutation_log 等は str を含むため str+int の TypeError を防ぐ
                        for k, v in value.items():
                            prev = aggregated_stats[key].get(k)
                            if isinstance(v, (int, float)) and isinstance(prev, (int, float)):
                                aggregated_stats[key][k] = prev + v
                            else:
                                aggregated_stats[key][k] = v
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
