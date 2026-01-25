"""
Quiz生成の再試行ロジック（目標数に達するまで複数回生成）

【初心者向け】
- 1 citation から1問（○のみ）を生成し、使用済み citation を記録して重複を防ぐ
- 試行ごとに batch で複数 citation を処理。規定数に達するか max_attempts まで繰り返す
- 重複・source不一致は除外。banned_statements で既出をLLMに伝え多様性を確保
"""
import logging
import random
import time
import unicodedata

from app.schemas.quiz import QuizGenerateRequest, QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.quiz.generator import generate_and_validate_quizzes
from app.quiz.duplicate_checker import is_duplicate_statement
from app.quiz.fixed_question_converter import apply_fixed_questions
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
    # 【新戦略】1つのcitationから1問（○のみ）を生成し、使用済みcitationを記録
    # これにより出題箇所の重複を必然的に避ける
    base_max_attempts = settings.quiz_max_attempts
    # 1回の試行で複数のcitationから並列生成するため、試行回数は目標数に応じて調整
    # 1回の試行で最大5問生成を想定
    calculated_max_attempts = max(base_max_attempts, (target_count // 5) + 2)
    max_attempts = calculated_max_attempts
    
    accepted_quizzes = []
    all_rejected_items = []
    all_attempt_errors = []
    aggregated_stats = {}
    
    # 重複チェック用: 既に採用されたstatementのリスト
    accepted_statements = []
    
    # 目標数に達するまで、または最大試行回数に達するまで繰り返す
    attempts = 0
    
    # 重複対策: 使用済みcitationsを記録（同じcitationから同じクイズが生成されるのを防ぐ）
    # 1つのcitationから1問のみ生成するため、citationの重複は必然的に避けられる
    used_citation_keys = set()
    
    # banned_statements: 既出・重複で落としたstatementを保持（retry時にLLMに渡す）
    banned_statements = []
    banned_statements_max = 30  # 上限（長くなりすぎないように）
    
    # 無限ループ防止: 連続重複回数とタイムアウト管理
    consecutive_duplicates = 0  # 連続重複回数
    max_consecutive_duplicates = 5  # 最大連続重複回数（5回続いたら早期終了）
    start_time = time.perf_counter()
    max_total_time_sec = settings.ollama_timeout_sec * 2  # LLMタイムアウトの2倍を全体タイムアウトとする
    
    logger.info(
        f"[GENERATION_RETRY] 開始: target={target_count}, max_attempts={max_attempts} "
        f"(base={base_max_attempts}, calculated={calculated_max_attempts}), "
        f"strategy=1問ずつ生成方式（citationごとに1問生成→使用済みcitationを除外）, "
        f"max_time_sec={max_total_time_sec}"
    )
    
    while len(accepted_quizzes) < target_count and attempts < max_attempts:
        attempts += 1
        
        # タイムアウトチェック
        elapsed_time = time.perf_counter() - start_time
        if elapsed_time > max_total_time_sec:
            logger.warning(
                f"[GENERATION_RETRY] タイムアウト: {elapsed_time:.1f}秒経過 "
                f"(max={max_total_time_sec}秒), accepted={len(accepted_quizzes)}, target={target_count}"
            )
            break
        
        # 残り必要数
        remaining = target_count - len(accepted_quizzes)
        
        logger.info(
            f"[GENERATION_RETRY] attempt={attempts}/{max_attempts}, "
            f"accepted={len(accepted_quizzes)}, target={target_count}, remaining={remaining}, "
            f"elapsed={elapsed_time:.1f}s, consecutive_duplicates={consecutive_duplicates}"
        )
        
        try:
            # 【ステップ1】使用済みcitationsを除外したcitationsを取得
            # 同じcitationから同じクイズが生成されるのを防ぐため、既に使用したcitationは除外
            # citation_keyは (source, page, quote先頭60文字) のタプルで一意性を保証
            available_citations = [
                c for c in citations
                if (c.source, c.page, c.quote[:60] if c.quote else "") not in used_citation_keys
            ]
            
            # 【デバッグ】使用可能なcitationsのsource分布を確認
            if available_citations:
                available_sources = {}
                for c in available_citations:
                    available_sources[c.source] = available_sources.get(c.source, 0) + 1
                logger.info(
                    f"[GENERATION_RETRY] 使用可能なcitationsのsource分布: {available_sources}, "
                    f"expected_source={request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else 'N/A'}"
                )
            
            # 【品質担保】使用可能なcitationsが少ない場合の処理
            # リセットロジックを改善：目標数に達していない場合のみリセット
            # ただし、リセットしても目標数に達しない可能性があるため、早期終了を検討
            remaining = target_count - len(accepted_quizzes)
            
            if len(available_citations) < remaining and len(accepted_quizzes) < target_count:
                logger.warning(
                    f"[GENERATION_RETRY] 使用可能なcitationsが不足 "
                    f"(available={len(available_citations)}, remaining={remaining}, accepted={len(accepted_quizzes)})"
                )
                
                # リセットしても意味がない場合は早期終了
                if len(citations) < remaining:
                    logger.error(
                        f"[GENERATION_RETRY] 全citations数({len(citations)})が残り必要数({remaining})を下回るため、早期終了します"
                    )
                    break
                
                # リセットして再試行（ただし、リセット回数を制限）
                if attempts < max_attempts - 1:  # 最後の試行ではリセットしない
                    logger.info(
                        f"[GENERATION_RETRY] 使用済みリストをリセット "
                        f"(available={len(available_citations)}, accepted={len(accepted_quizzes)}, remaining={remaining})"
                    )
                    used_citation_keys.clear()
                    available_citations = citations
                else:
                    logger.warning(
                        f"[GENERATION_RETRY] 最後の試行のため、リセットせずに続行します"
                    )
            
            # 【ステップ2】残り必要数を計算し、1回の試行で生成するbatch_sizeを決定
            # 1回の試行で最大5問生成を想定（効率化のため並列生成）
            remaining = target_count - len(accepted_quizzes)
            batch_size = min(5, remaining, len(available_citations))
            
            # 【ステップ3】使用可能なcitationsからbatch_size件をランダムに選択
            # 1回の試行で複数問を並列生成するため、複数のcitationを選択
            if len(available_citations) >= batch_size:
                selected_citations_list = random.sample(available_citations, batch_size)
            else:
                selected_citations_list = available_citations[:batch_size] if len(available_citations) > 0 else []
            
            if len(selected_citations_list) == 0:
                logger.warning("[GENERATION_RETRY] 使用可能なcitationsがありません")
                break
            
            # 【ステップ4】各citationから1問（○のみ）を生成
            # 新戦略: 1つのcitationから1問のみ生成し、使用済みcitationを記録することで重複を防ぐ
            batch_quizzes = []  # 生成されたクイズのリスト（(quiz, citation)のタプル）
            batch_rejected = []  # バリデーション失敗したアイテム情報
            batch_attempt_errors = []  # 試行ごとの失敗履歴
            batch_stats = {}  # 統計情報（生成数、却下理由など）
            
            # 【ステップ5】並列生成の準備（効率化のため複数のcitationを同時に処理）
            # 各citationに対してgenerate_and_validate_quizzesを呼び出すタスクを作成
            import asyncio
            generation_tasks = []
            for citation_idx, single_citation in enumerate(selected_citations_list):
                # debugログ: selected_citationを出力
                expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                # Unicode正規化して比較（NFC正規化）
                if expected_source:
                    expected_source_norm = unicodedata.normalize("NFC", expected_source)
                    actual_source_norm = unicodedata.normalize("NFC", single_citation.source)
                    source_match = "✅" if actual_source_norm == expected_source_norm else "❌"
                else:
                    source_match = "❓"
                logger.info(
                    f"[GENERATION:SELECTED_CITATION] citation_idx={citation_idx}, "
                    f"source={single_citation.source} {source_match}, "
                    f"expected={expected_source}, page={single_citation.page}, "
                    f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                )
                
                # 【品質担保】選択されたcitationのsourceが指定ソースと一致することを確認
                if expected_source:
                    # Unicode正規化して比較（NFC正規化）
                    expected_source_norm = unicodedata.normalize("NFC", expected_source)
                    actual_source_norm = unicodedata.normalize("NFC", single_citation.source)
                    if actual_source_norm != expected_source_norm:
                        logger.error(
                            f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致: "
                            f"expected={expected_source} (norm={expected_source_norm}), "
                            f"actual={single_citation.source} (norm={actual_source_norm}), "
                            f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                        )
                        # このcitationをスキップ
                        continue
                
                # 1つのcitationから1問（○のみ）を生成
                task = generate_and_validate_quizzes(
                    level=request.level,
                    count=1,  # 1問ずつ生成
                    topic=request.topic,
                    citations=[single_citation],  # 1つのcitationのみを使用
                    request_id=request_id,
                    attempt_index=f"{attempts}-{citation_idx}",
                    banned_statements=banned_statements if len(banned_statements) > 0 else None,
                )
                # 【品質担保】選択されたcitationのsourceが指定ソースと一致することを確認（事前チェック）
                expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                if expected_source:
                    # Unicode正規化して比較（NFC正規化）
                    expected_source_norm = unicodedata.normalize("NFC", expected_source)
                    actual_source_norm = unicodedata.normalize("NFC", single_citation.source)
                    if actual_source_norm != expected_source_norm:
                        logger.error(
                            f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致（事前チェック）: "
                            f"expected={expected_source} (norm={expected_source_norm}), "
                            f"actual={single_citation.source} (norm={actual_source_norm}), "
                            f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                        )
                        # このcitationをスキップ（タスクに追加しない）
                        continue
                
                generation_tasks.append((task, single_citation, citation_idx))
            
            # 並列実行
            for task, single_citation, citation_idx in generation_tasks:
                try:
                    quiz_accepted, quiz_rejected, quiz_attempt_errors, quiz_stats = await task
                    
                    # 統計情報をマージ
                    for key, value in quiz_stats.items():
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
                    
                    batch_rejected.extend(quiz_rejected)
                    batch_attempt_errors.extend(quiz_attempt_errors)
                    
                    # ○のみを採用（×は生成しない）
                    quiz_true = [q for q in quiz_accepted if q.answer_bool]
                    
                    if len(quiz_true) > 0:
                        # citationを確実に紐付け
                        selected_quiz = quiz_true[0]
                        corresponding_citation = single_citation
                        
                        # 【品質担保】citationのsourceが指定ソースと一致することを確認
                        # （念のため二重チェック、retrievalでフィルタ済みだが念のため）
                        if corresponding_citation and corresponding_citation.source:
                            # request.source_idsが1件であることはrouterで保証済み
                            expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                            if expected_source:
                                # Unicode正規化して比較（NFC正規化）
                                expected_source_norm = unicodedata.normalize("NFC", expected_source)
                                actual_source_norm = unicodedata.normalize("NFC", corresponding_citation.source)
                                if actual_source_norm != expected_source_norm:
                                    logger.error(
                                        f"[GENERATION:SOURCE_MISMATCH] citationのsourceが不一致: "
                                        f"expected={expected_source} (norm={expected_source_norm}), "
                                        f"actual={corresponding_citation.source} (norm={actual_source_norm}), "
                                        f"quiz_statement={selected_quiz.statement[:50]}"
                                    )
                                    all_rejected_items.append({
                                        "statement": selected_quiz.statement[:100],
                                        "reason": "source_mismatch",
                                    })
                                    continue
                        
                        # 【ステップ6】statementの重複チェック
                        # duplicate_checkerモジュールの関数を使用して、既存のstatementと重複していないか確認
                        # 重複判定は2段階: 1) 通常の正規化（空白・句読点除去）で完全一致、2) コア内容キー（否定語除去後）で一致
                        if is_duplicate_statement(selected_quiz.statement, accepted_statements):
                            consecutive_duplicates += 1
                            # 【デバッグ】重複クイズのsource情報を出力
                            quiz_sources = [c.source for c in selected_quiz.citations] if selected_quiz.citations else []
                            expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                            logger.warning(
                                f"重複クイズを除外: '{selected_quiz.statement[:50]}...' "
                                f"(consecutive_duplicates={consecutive_duplicates}/{max_consecutive_duplicates}), "
                                f"quiz_sources={quiz_sources}, expected_source={expected_source}"
                            )
                            all_rejected_items.append({
                                "statement": selected_quiz.statement[:100],
                                "reason": "duplicate_statement",
                                "quiz_sources": quiz_sources,
                                "expected_source": expected_source,
                            })
                            # 【重要】重複したstatementをbanned_statementsに追加（次回のLLM生成で除外）
                            if len(banned_statements) < banned_statements_max:
                                banned_statements.append(selected_quiz.statement)
                                logger.info(
                                    f"[GENERATION_RETRY] 重複statementをbanned_statementsに追加: "
                                    f"'{selected_quiz.statement[:50]}...' (total={len(banned_statements)})"
                                )
                            continue
                        
                        # 重複がなかった場合はリセット
                        consecutive_duplicates = 0
                        
                        # 【ステップ7】citationsの紐付け（品質担保）
                        # LLM出力のcitationsを無視し、生成に使ったsingle_citationを必ず付与
                        # これにより、どのcitationから生成されたかが明確になる
                        # quiz.citationsは最低1件保証（single_citation）
                        # 同一sourceで最大2件まで追加は任意（LLMが追加したcitationがあれば採用）
                        if corresponding_citation:
                            # LLM出力のcitationsを無視し、single_citationを先頭に配置
                            # 同一sourceのcitationsを最大2件まで追加（single_citation + 追加1件）
                            llm_citations = selected_quiz.citations if selected_quiz.citations else []
                            
                            # 同一sourceのcitationsを抽出（single_citation以外）
                            same_source_citations = [
                                c for c in llm_citations
                                if c.source == corresponding_citation.source
                                and not (
                                    c.source == corresponding_citation.source
                                    and c.page == corresponding_citation.page
                                    and (c.quote[:60] if c.quote else "") == (corresponding_citation.quote[:60] if corresponding_citation.quote else "")
                                )
                            ]
                            
                            # single_citationを先頭に配置し、同一sourceのcitationsを最大1件追加（合計最大2件）
                            final_citations = [corresponding_citation]
                            if len(same_source_citations) > 0:
                                final_citations.append(same_source_citations[0])
                            
                            selected_quiz = selected_quiz.model_copy(update={"citations": final_citations})
                            logger.info(
                                f"[GENERATION:CITATION_ASSIGNED] single_citationを必ず付与（LLM出力無視）: "
                                f"source={corresponding_citation.source}, page={corresponding_citation.page}, "
                                f"final_citations_count={len(final_citations)}"
                            )
                        else:
                            logger.warning(f"[GENERATION:CITATION_MISSING] corresponding_citationが見つかりません（citation_idx={citation_idx}）")
                        
                        # 採用
                        batch_quizzes.append((selected_quiz, single_citation))
                        accepted_statements.append(selected_quiz.statement)
                        
                        # 【重要】採用されたstatementをbanned_statementsに追加（次回の生成で除外）
                        if len(banned_statements) < banned_statements_max:
                            banned_statements.append(selected_quiz.statement)
                            logger.debug(
                                f"[GENERATION_RETRY] 採用されたstatementをbanned_statementsに追加: "
                                f"'{selected_quiz.statement[:50]}...' (total={len(banned_statements)})"
                            )
                        
                        # debugログ
                        final_citations_count = len(selected_quiz.citations)
                        selected_citation_info = f"{corresponding_citation.source}(p.{corresponding_citation.page})" if corresponding_citation else "NONE"
                        logger.info(
                            f"[GENERATION:DEBUG] citation {citation_idx+1}/{batch_size}: 生成成功, "
                            f"selected_citation={selected_citation_info}, "
                            f"final_citations_count={final_citations_count}, "
                            f"quiz_statement_preview={selected_quiz.statement[:50]}"
                        )
                    else:
                        logger.warning(
                            f"[GENERATION_RETRY] citation {citation_idx+1}/{batch_size}: 生成失敗（○が生成されませんでした）"
                        )
                except Exception as e:
                    logger.error(f"[GENERATION_RETRY] citation {citation_idx+1}/{batch_size} でエラー: {type(e).__name__}: {e}")
            
            # 連続重複が多すぎる場合は早期終了
            should_break_outer = False
            if consecutive_duplicates >= max_consecutive_duplicates:
                logger.error(
                    f"[GENERATION_RETRY] 連続重複が{consecutive_duplicates}回続いたため、早期終了します。"
                    f"accepted={len(accepted_quizzes)}, target={target_count}"
                )
                should_break_outer = True
            
            # 結果を集計
            new_accepted_quizzes = []
            for selected_quiz, single_citation in batch_quizzes:
                new_accepted_quizzes.append(selected_quiz)
                
                # 使用済みcitationsを記録（このcitationは使用済みとしてマーク）
                citation_key = (
                    single_citation.source,
                    single_citation.page,
                    single_citation.quote[:60] if single_citation.quote else ""
                )
                used_citation_keys.add(citation_key)
            
            # 連続重複が多すぎる場合は早期終了（フラグで外側のwhileループも抜ける）
            if should_break_outer:
                logger.error(
                    f"[GENERATION_RETRY] 連続重複が{consecutive_duplicates}回続いたため、試行を中断します。"
                )
                break  # 外側のwhileループを抜ける
            
            # 結果を集計
            accepted_quizzes.extend(new_accepted_quizzes)
            all_rejected_items.extend(batch_rejected)
            all_attempt_errors.extend(batch_attempt_errors)
            
            # 新規採用が0件で、連続重複が続いている場合はbanned_statementsをクリア（多様性確保）
            if len(new_accepted_quizzes) == 0 and consecutive_duplicates >= 3:
                logger.info(
                    f"[GENERATION_RETRY] 新規採用0件かつ連続重複{consecutive_duplicates}回のため、"
                    f"banned_statementsをクリアして多様性を確保します"
                )
                banned_statements.clear()
                used_citation_keys.clear()  # citationsもリセット
            
            # 【重要】rejected_itemsから重複statementをbanned_statementsに追加
            for rejected_item in batch_rejected:
                if rejected_item.get("reason") == "duplicate_statement":
                    statement = rejected_item.get("statement", "")
                    if statement and statement not in banned_statements and len(banned_statements) < banned_statements_max:
                        banned_statements.append(statement)
                        logger.info(
                            f"[GENERATION_RETRY] rejected_itemからbanned_statementsに追加: "
                            f"'{statement[:50]}...' (total={len(banned_statements)})"
                        )
            
            logger.info(
                f"[GENERATION_RETRY] attempt={attempts} 完了: "
                f"quizzes_generated={len(batch_quizzes)}, accepted={len(new_accepted_quizzes)}, "
                f"rejected={len(batch_rejected)}, total_accepted={len(accepted_quizzes)}, "
                f"consecutive_duplicates={consecutive_duplicates}"
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
            
            # タイムアウトチェック
            elapsed_time = time.perf_counter() - start_time
            if elapsed_time > max_total_time_sec:
                logger.warning(f"[GENERATION_RETRY] タイムアウトのため終了: {elapsed_time:.1f}秒経過")
                break
            
            # 最大試行回数に達した場合は終了
            if attempts >= max_attempts:
                break
    
    # 【ステップ8】生成数の調整
    # 確率的選択により既にバランスが取れているため、そのまま使用
    # ただし、目標数を超えている場合はスライスして目標数に合わせる
    if len(accepted_quizzes) > target_count:
        logger.info(f"生成数が目標数（{target_count}問）を超えています（{len(accepted_quizzes)}問）。目標数にスライスします。")
        accepted_quizzes = accepted_quizzes[:target_count]
    
    # 【ステップ9】固定問題の変換（4問目と5問目を×問題に固定）
    # fixed_question_converterモジュールの関数を使用して、○問題を×問題に変換
    # これにより、クイズセットに必ず×問題が含まれるようになる
    accepted_quizzes = apply_fixed_questions(accepted_quizzes)
    
    # 経過時間を計算
    total_elapsed_time = time.perf_counter() - start_time
    
    # 目標数に達したかどうか
    exhausted = len(accepted_quizzes) < target_count
    
    # エラー情報を構築
    error_info = None
    if exhausted and len(accepted_quizzes) == 0:
        if total_elapsed_time > max_total_time_sec:
            error_info = {
                "type": "timeout",
                "message": f"タイムアウト（{total_elapsed_time:.1f}秒経過）のため、クイズが生成できませんでした",
            }
        elif consecutive_duplicates >= max_consecutive_duplicates:
            error_info = {
                "type": "duplicate_loop",
                "message": f"連続重複が{consecutive_duplicates}回続いたため、クイズ生成を中断しました",
            }
        else:
            error_info = {
                "type": "generation_failed",
                "message": f"最大試行回数（{max_attempts}回）に達しましたが、クイズが生成できませんでした",
            }
    elif exhausted:
        error_info = {
            "type": "partial_success",
            "message": f"目標数（{target_count}問）に達しませんでした（生成数: {len(accepted_quizzes)}問）",
        }
    
    # 最後に選べたcitation数を計算
    final_available_citations = len([
        c for c in citations
        if (c.source, c.page, c.quote[:60] if c.quote else "") not in used_citation_keys
    ])
    
    # 最終的な統計情報
    aggregated_stats["attempts"] = attempts
    aggregated_stats["exhausted"] = exhausted
    aggregated_stats["generated_count"] = len(accepted_quizzes)
    aggregated_stats["target_count"] = target_count
    aggregated_stats["final_true_count"] = len([q for q in accepted_quizzes if q.answer_bool])
    aggregated_stats["final_false_count"] = len([q for q in accepted_quizzes if not q.answer_bool])
    aggregated_stats["final_available_citations"] = final_available_citations
    aggregated_stats["total_citations"] = len(citations)
    
    logger.info(
        f"[GENERATION_RETRY] 完了: "
        f"attempts={attempts}, accepted={len(accepted_quizzes)}, target={target_count}, "
        f"exhausted={exhausted}, elapsed={total_elapsed_time:.1f}s, "
        f"consecutive_duplicates={consecutive_duplicates}, "
        f"final_available_citations={final_available_citations}"
    )
    
    return (
        accepted_quizzes,
        all_rejected_items,
        error_info,
        attempts,
        all_attempt_errors,
        aggregated_stats,
    )
