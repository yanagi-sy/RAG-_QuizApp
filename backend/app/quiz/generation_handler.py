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
    import time
    
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
            # 使用済みcitationsを除外したcitationsを取得
            available_citations = [
                c for c in citations
                if create_citation_key(c) not in used_citation_keys
            ]
            
<<<<<<< HEAD
            # 【デバッグ】使用可能なcitationsのsource分布を確認
            if available_citations:
                available_sources = {}
                for c in available_citations:
                    available_sources[c.source] = available_sources.get(c.source, 0) + 1
=======
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
>>>>>>> ai-generated
                logger.info(
                    f"[GENERATION_RETRY] 使用可能なcitationsのsource分布: {available_sources}, "
                    f"expected_source={request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else 'N/A'}"
                )
<<<<<<< HEAD
            
            # 【品質担保】使用可能なcitationsが少ない場合の処理
            # リセットロジックを改善：目標数に達していない場合のみリセット
            # ただし、リセットしても目標数に達しない可能性があるため、早期終了を検討
            remaining = target_count - len(accepted_quizzes)
            
            if len(available_citations) < remaining and len(accepted_quizzes) < target_count:
=======
                
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
>>>>>>> ai-generated
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
            
            # 残り必要数を計算（1回の試行で最大5問生成を想定）
            remaining = target_count - len(accepted_quizzes)
            batch_size = min(5, remaining, len(available_citations))
            
            # 使用可能なcitationsからbatch_size件を選択（1回の試行で複数問生成）
            if len(available_citations) >= batch_size:
                selected_citations_list = random.sample(available_citations, batch_size)
            else:
                selected_citations_list = available_citations[:batch_size] if len(available_citations) > 0 else []
            
            if len(selected_citations_list) == 0:
                logger.warning("[GENERATION_RETRY] 使用可能なcitationsがありません")
                break
            
            # 【新戦略】各citationから1問（○のみ）を生成
            batch_quizzes = []  # 生成されたクイズのリスト
            batch_rejected = []
            batch_attempt_errors = []
            batch_stats = {}
            
            # 並列生成（効率化のため）
            import asyncio
            generation_tasks = []
            for citation_idx, single_citation in enumerate(selected_citations_list):
                # debugログ: selected_citationを出力
                expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                source_match = "✅" if single_citation.source == expected_source else "❌"
                logger.info(
                    f"[GENERATION:SELECTED_CITATION] citation_idx={citation_idx}, "
                    f"source={single_citation.source} {source_match}, "
                    f"expected={expected_source}, page={single_citation.page}, "
                    f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                )
                
                # 【デバッグ】citationのquoteの内容を確認（火災関連キーワードチェック）
                fire_keywords = ["火災", "避難", "災害", "防犯"]
                quote_has_fire = any(keyword in single_citation.quote for keyword in fire_keywords) if single_citation.quote else False
                if quote_has_fire:
                    logger.info(
                        f"[GENERATION:DEBUG] citationのquoteに火災関連キーワードを検出: "
                        f"source={single_citation.source}, quote_preview={single_citation.quote[:100]}..., "
                        f"fire_keywords={[kw for kw in fire_keywords if kw in single_citation.quote]}"
                    )
                
                # 【品質担保】選択されたcitationのsourceが指定ソースと一致することを確認
                if expected_source and single_citation.source != expected_source:
                    logger.error(
                        f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致: "
                        f"expected={expected_source}, actual={single_citation.source}, "
                        f"quote_preview={single_citation.quote[:50] if single_citation.quote else 'N/A'}"
                    )
                    # このcitationをスキップ
                    continue
                
                # 【品質担保】citationのsourceとquoteの内容が一致しているか確認
                # 火災関連のキーワードが含まれている場合、sourceがsample*.txtでないことを確認
                fire_keywords = ["火災", "避難", "災害", "防犯"]
                has_fire_content = any(keyword in single_citation.quote for keyword in fire_keywords)
                
                # sample*.txtファイルに火災関連の内容が含まれている場合は不一致として検出
                if has_fire_content and single_citation.source.startswith("sample") and single_citation.source.endswith(".txt"):
                    logger.error(
                        f"[GENERATION:CONTENT_MISMATCH] 【重大】選択されたcitationのsourceと内容の不一致を検出: "
                        f"source={single_citation.source}, quote_preview={single_citation.quote[:100]}..., "
                        f"fire_keywords={[kw for kw in fire_keywords if kw in single_citation.quote]}"
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
                if expected_source and single_citation.source != expected_source:
                    logger.error(
                        f"[GENERATION:SOURCE_MISMATCH] 選択されたcitationのsourceが不一致（事前チェック）: "
                        f"expected={expected_source}, actual={single_citation.source}, "
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
                            if expected_source and corresponding_citation.source != expected_source:
                                logger.error(
                                    f"[GENERATION:SOURCE_MISMATCH] citationのsourceが不一致: "
                                    f"expected={expected_source}, actual={corresponding_citation.source}, "
                                    f"quiz_statement={selected_quiz.statement[:50]}"
                                )
                                all_rejected_items.append({
                                    "statement": selected_quiz.statement[:100],
                                    "reason": "source_mismatch",
                                })
                                continue
                        
                        # 【品質担保】statementに火災関連キーワードが含まれている場合、sourceがsample*.txtでないことを確認
                        # （statementに火災関連の内容が含まれているのに、citationのsourceがsample*.txtの場合は不一致）
                        fire_keywords = ["火災", "避難", "災害", "防犯"]
                        statement_has_fire = any(keyword in selected_quiz.statement for keyword in fire_keywords)
                        
                        if statement_has_fire and corresponding_citation and corresponding_citation.source:
                            # sample*.txtファイルに火災関連の内容が含まれている場合は不一致として検出
                            if corresponding_citation.source.startswith("sample") and corresponding_citation.source.endswith(".txt"):
                                logger.error(
                                    f"[GENERATION:STATEMENT_CONTENT_MISMATCH] 【重大】statementに火災関連内容があるのにcitationのsourceがsample*.txt: "
                                    f"statement='{selected_quiz.statement[:50]}...', "
                                    f"citation_source={corresponding_citation.source}, "
                                    f"citation_quote_preview={corresponding_citation.quote[:100] if corresponding_citation.quote else 'N/A'}..., "
                                    f"fire_keywords={[kw for kw in fire_keywords if kw in selected_quiz.statement]}"
                                )
                                all_rejected_items.append({
                                    "statement": selected_quiz.statement[:100],
                                    "reason": "statement_content_mismatch",
                                    "citation_source": corresponding_citation.source,
                                    "fire_keywords": [kw for kw in fire_keywords if kw in selected_quiz.statement],
                                })
                                continue
                        
                        # statementの重複チェック
                        if _is_duplicate(selected_quiz.statement, accepted_statements):
                            consecutive_duplicates += 1
                            # 【デバッグ】重複クイズのsource情報を出力
                            quiz_sources = [c.source for c in selected_quiz.citations] if selected_quiz.citations else []
                            expected_source = request.source_ids[0] if request.source_ids and len(request.source_ids) > 0 else None
                            
                            # 【デバッグ】statementに火災関連キーワードが含まれている場合、citationのquoteも確認
                            if statement_has_fire:
                                citation_quotes = [c.quote[:100] if c.quote else "N/A" for c in selected_quiz.citations] if selected_quiz.citations else []
                                logger.error(
                                    f"[GENERATION:DUPLICATE_FIRE] 重複クイズ（火災関連）を除外: "
                                    f"statement='{selected_quiz.statement[:50]}...', "
                                    f"quiz_sources={quiz_sources}, expected_source={expected_source}, "
                                    f"citation_quotes={citation_quotes}"
                                )
                            
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
                            continue
                        
                        # 重複がなかった場合はリセット
                        consecutive_duplicates = 0
                        
                        # 【品質担保】citationsはLLM出力を無視し、生成に使ったsingle_citationを必ず付与
                        # quiz.citationsは最低1件保証（single_citation）
                        # 同一sourceで最大2件まで追加は任意
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
    
    # 【新戦略】確率的選択により既にバランスが取れているため、そのまま使用
    # ただし、目標数を超えている場合はスライス
    if len(accepted_quizzes) > target_count:
        logger.info(f"生成数が目標数（{target_count}問）を超えています（{len(accepted_quizzes)}問）。目標数にスライスします。")
        accepted_quizzes = accepted_quizzes[:target_count]
    
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
