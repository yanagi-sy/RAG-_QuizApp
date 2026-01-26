"""
LLMによるクイズ生成（1回分の生成＋バリデーション）

【初心者向け】
- プロンプト構築 → Ollama 呼び出し（Quiz用オプション）→ JSONパース → バリデーション
- 修復用プロンプトで1回リトライ。採用/却下アイテムと統計を返す
- generation_handler から複数回呼ばれ、目標数に達するまで試行
"""
import asyncio
import json
import logging
import uuid

from app.core.settings import settings
from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.llm.base import LLMInternalError, LLMTimeoutError
from app.llm import get_llm_client
from app.llm.prompt import build_quiz_generation_messages, build_quiz_json_fix_messages
from app.quiz.parser import parse_quiz_json
from app.quiz.validator import validate_quiz_item
from app.quiz.mutator import make_false_statement
from app.quiz.postprocess import postprocess_quiz_item

# ロガー設定
logger = logging.getLogger(__name__)

# 否定語パターン（LLMが勝手に×を作るのを防ぐ）
NEGATIVE_PATTERNS = [
    r'しない',
    r'ではない',
    r'ではありません',
    r'とは限らない',
    r'禁止',
    r'不要',
    r'必要ない',
    r'してはいけない',
    r'してはならない',
    r'すべきではない',
]


def _contains_negative_phrase(statement: str) -> bool:
    """
    statement に否定語が含まれているかチェック
    
    Args:
        statement: クイズの statement
        
    Returns:
        True: 否定語が含まれている（×問題の可能性）
        False: 否定語が含まれていない（○問題）
    """
    import re
    for pattern in NEGATIVE_PATTERNS:
        if re.search(pattern, statement):
            return True
    return False


async def generate_and_validate_quizzes(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
    request_id: str | None = None,
    attempt_index: int | None = None,
    banned_statements: list[str] | None = None,
) -> tuple[list[QuizItemSchema], list[dict], list[dict], dict]:
    """
    LLMでクイズを生成し、バリデーションを行う（○のみ生成、×はオプション）
    
    **重要**: この関数は count=1 専用です。複数問生成する場合は Router側でループしてください。
    
    戦略:
    1. LLMに1問の「正しい断言文（○）」を生成させる
    2. item を validator でチェックし、合格したものを採用
    3. （オプション）採用した item から、mutator で「×」を生成
    4. （オプション）×もvalidatorでチェックし、合格したものを採用
    5. 最終的に○のみ、または○と×の組み合わせを返す
    
    **注意**: generation_handler.pyでは○のみを採用し、×は無視されます。
    効率化のため、×生成をスキップするオプションを追加することも検討できます。
    
    Args:
        level: 難易度
        count: 生成数（count > 1 の場合は1に制限されます）
        topic: トピック
        citations: 引用リスト
        
    Returns:
        (accepted_quizzes, rejected_items, attempt_errors, generation_stats) のタプル
        - accepted_quizzes: バリデーション通過したクイズのリスト（○1件、または○1件+×1件）
        - rejected_items: バリデーション失敗したアイテム情報のリスト
        - attempt_errors: 試行ごとの失敗履歴（途中失敗を含む）
        - generation_stats: 生成統計（generated_true_count, generated_false_count, dropped_reasons）
    """
    # count=1 専用制限（複数問は Router側でループ）
    if count > 1:
        logger.warning(f"count={count} が指定されましたが、この関数は count=1 専用です。count=1 に制限します。")
        count = 1
    
    # settings をインポート（LLMパラメータ取得用）
    from app.core.settings import settings
    from app.llm.prompt import build_quiz_generation_messages
    
    # prompt_statsを先に取得（エラー時も保持するため）
    ret = build_quiz_generation_messages(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
        banned_statements=banned_statements,
    )
    
    # 互換対応: (messages, prompt_stats) または messages のみ
    if isinstance(ret, tuple) and len(ret) == 2:
        _, prompt_stats = ret
    else:
        prompt_stats = {}
    
    # LLMパラメータをprompt_statsに事前追加（エラー時も必ず含まれる）
    prompt_stats["llm_num_predict"] = settings.quiz_ollama_num_predict
    prompt_stats["llm_temperature"] = settings.quiz_ollama_temperature
    prompt_stats["llm_timeout_sec"] = settings.ollama_timeout_sec
    
    attempt_errors = []
    raw_true_quizzes = []
    
    try:
        # LLMで○（正しい断言文）を生成（JSONパースまで、attempt_errors と prompt_stats を含む）
        raw_true_quizzes, attempt_errors, llm_prompt_stats = await generate_quizzes_with_llm(
            level=level,
            count=count,
            topic=topic,
            citations=citations,
            request_id=request_id,
            attempt_index=attempt_index,
            banned_statements=banned_statements,
        )
        
        # LLM呼び出しで更新されたprompt_stats（llm_output_charsなど）をマージ
        prompt_stats.update(llm_prompt_stats)
        
    except Exception as e:
        # エラー時もprompt_statsを保持したまま処理を続行
        logger.error(f"generate_quizzes_with_llm でエラー: {type(e).__name__}: {e}")
        
        # LLM生出力が取得できていない場合は0を設定
        if "llm_output_chars" not in prompt_stats:
            prompt_stats["llm_output_chars"] = 0
            prompt_stats["llm_output_preview_head"] = ""
        
        # エラー情報をattempt_errorsに追加
        if not attempt_errors:
            attempt_errors = [{
                "attempt": 1,
                "stage": "llm_or_parse",
                "type": type(e).__name__,
                "message": str(e),
            }]
        
        # 空のクイズリストで続行（prompt_statsとattempt_errorsは保持）
        raw_true_quizzes = []
    
    # バリデーション & false_statement処理（LLM優先、Mutator保険）
    accepted_true = []  # 採用された○
    accepted_false = []  # 採用された×
    rejected = []  # 不合格アイテム
    dropped_reasons = {}  # reason -> count の集計
    llm_negative_rejected_count = 0  # LLM由来の否定文reject数
    llm_false_generated_count = 0  # LLM由来の×生成数
    mutator_false_generated_count = 0  # mutator由来の×生成数
    sample_mutation_log = None  # true->false の例
    false_source_stats = {"llm": 0, "mutator": 0, "none": 0}  # false_statement生成元の統計
    
    for quiz in raw_true_quizzes:
        # 【修正】後処理を先に実行（statement正規化、explanation固定、citations選別）
        try:
            processed_quiz = postprocess_quiz_item(quiz)
        except Exception as e:
            logger.warning(f"後処理失敗: {e}、元のクイズを使用")
            processed_quiz = quiz
        
        # dict に変換してバリデーション（○）
        quiz_dict = processed_quiz.model_dump() if hasattr(processed_quiz, "model_dump") else processed_quiz.dict()
        statement = quiz_dict.get("statement", "")
        
        # 否定語チェック（LLMが勝手に×を作るのを防ぐ）
        if _contains_negative_phrase(statement):
            logger.warning(f"LLM由来の否定文を reject: {statement[:50]}")
            rejected.append({
                "statement": statement[:100],
                "reason": "llm_negative_phrase",
            })
            dropped_reasons["llm_negative_phrase"] = dropped_reasons.get("llm_negative_phrase", 0) + 1
            llm_negative_rejected_count += 1
            continue
        
        # validator チェック（○）
        ok, reason = validate_quiz_item(quiz_dict)
        
        if ok:
            # ○として採用（正規化済み）
            accepted_true.append(processed_quiz)
            
            # ×を生成（LLM優先、Mutator保険）
            original_statement = quiz_dict["statement"]
            false_statement = None
            false_source = "none"  # デフォルトは none
            
            # false_statementがLLMから返されているかチェック
            llm_false_statement = quiz_dict.get("false_statement")
            if llm_false_statement and isinstance(llm_false_statement, str) and llm_false_statement.strip():
                false_statement = llm_false_statement.strip()
                false_source = "llm"
                logger.info(f"LLM由来のfalse_statementを使用: {false_statement[:50]}...")
            else:
                # false_statementがない or 空の場合、Mutatorで生成（保険）
                logger.info(f"LLM由来のfalse_statementがないため、Mutatorで生成")
                
                # [観測ログA] Mutator直前のstatement確認
                # TypeError対策: request_idとattempt_indexを文字列に変換
                request_id_str = str(request_id) if request_id is not None else "None"
                attempt_index_str = str(attempt_index) if attempt_index is not None else "None"
                logger.info(
                    f"[PIPE:BEFORE_MUTATOR] "
                    f"request_id={request_id_str}, attempt_index={attempt_index_str}, "
                    f"statement_preview={original_statement[:120]}, "
                    f"statement_len={len(original_statement)}"
                )
                
                # Mutatorで生成（複数回試行）
                false_statement = make_false_statement(original_statement)
                false_source = "mutator"
                
                # Mutatorが失敗した場合（元の文と同じ）、別の方法を試す
                if false_statement == original_statement:
                    logger.info("Mutator初回試行が失敗したため、代替方法を試行します")
                    
                    # 代替方法1: 文末の否定化を試す（より積極的）
                    alternative_patterns = [
                        (r"行う。$", "行わない。"),
                        (r"確認する。$", "確認しない。"),
                        (r"連絡する。$", "連絡しない。"),
                        (r"報告する。$", "報告しない。"),
                        (r"実施する。$", "実施しない。"),
                        (r"実行する。$", "実行しない。"),
                        (r"処理する。$", "処理しない。"),
                        (r"対応する。$", "対応しない。"),
                        (r"である。$", "ではない。"),
                        (r"する。$", "しない。"),
                        (r"できる。$", "できない。"),
                        (r"される。$", "されない。"),
                        (r"ある。$", "ない。"),
                    ]
                    
                    import re
                    for pattern, replacement in alternative_patterns:
                        if re.search(pattern, original_statement):
                            false_statement = re.sub(pattern, replacement, original_statement)
                            if false_statement != original_statement:
                                logger.info(f"代替方法で×問題を生成: パターン '{pattern}' を適用")
                                break
                    
                    # 代替方法2: "必ず"を削除して「行わなくてもよい」に変換
                    if false_statement == original_statement and "必ず" in original_statement:
                        false_statement = original_statement.replace("必ず", "").replace("  ", " ").strip()
                        if false_statement != original_statement:
                            logger.info("代替方法で×問題を生成: '必ず'を削除")
                    
                    # 代替方法3: "必須"を"任意"に変換
                    if false_statement == original_statement and "必須" in original_statement:
                        false_statement = original_statement.replace("必須", "任意")
                        if false_statement != original_statement:
                            logger.info("代替方法で×問題を生成: '必須'を'任意'に変換")
                    
                    # 代替方法4: "必要"を"不要"に変換
                    if false_statement == original_statement and "必要" in original_statement:
                        false_statement = original_statement.replace("必要", "不要")
                        if false_statement != original_statement:
                            logger.info("代替方法で×問題を生成: '必要'を'不要'に変換")
            
            # false_statementが取得できた場合のみ処理
            if false_statement and false_statement != original_statement:
                # ×がvalidatorを通過するかチェック
                false_quiz_dict = quiz_dict.copy()
                false_quiz_dict["id"] = str(uuid.uuid4())[:8]  # 新しいIDを生成
                false_quiz_dict["statement"] = false_statement
                false_quiz_dict["answer_bool"] = False  # 必ず False
                false_quiz_dict["false_statement"] = None  # ×問題にはfalse_statementは不要
                
                # validator チェック（×）
                ok_false, reason_false = validate_quiz_item(false_quiz_dict)
                
                if ok_false:
                    # ×として採用
                    false_quiz = QuizItemSchema(**false_quiz_dict)
                    accepted_false.append(false_quiz)
                    
                    # 統計更新
                    if false_source == "llm":
                        llm_false_generated_count += 1
                        false_source_stats["llm"] += 1
                    elif false_source == "mutator":
                        mutator_false_generated_count += 1
                        false_source_stats["mutator"] += 1
                    
                    # sample_mutation_log を1件だけ記録
                    if sample_mutation_log is None:
                        sample_mutation_log = {
                            "true_statement": original_statement[:50],
                            "false_statement": false_statement[:50],
                            "false_source": false_source,
                        }
                else:
                    # ×が不合格
                    logger.warning(f"False quiz バリデーション失敗 (source={false_source}): {reason_false}")
                    rejected.append({
                        "statement": false_statement[:100],
                        "reason": f"false:{reason_false}",
                        "false_source": false_source,
                    })
                    # dropped_reasons に集計
                    dropped_key = f"false:{reason_false}"
                    dropped_reasons[dropped_key] = dropped_reasons.get(dropped_key, 0) + 1
                    false_source_stats["none"] += 1
            else:
                # false_statementが取得できなかった or 元と同じ
                logger.warning(f"False statementの生成に失敗 (source={false_source})")
                rejected.append({
                    "statement": original_statement[:100],
                    "reason": "false_generation_failed",
                    "false_source": false_source,
                })
                dropped_reasons["false_generation_failed"] = dropped_reasons.get("false_generation_failed", 0) + 1
                false_source_stats["none"] += 1
        else:
            # ○が不合格
            logger.warning(f"True quiz バリデーション失敗: {reason}")
            rejected.append({
                "statement": quiz_dict.get("statement", quiz_dict.get("question", ""))[:100],
                "reason": f"true:{reason}",
            })
            # dropped_reasons に集計
            dropped_key = f"true:{reason}"
            dropped_reasons[dropped_key] = dropped_reasons.get(dropped_key, 0) + 1
    
    # ○と×を交互に配置（バランス良く）
    accepted = []
    for i in range(max(len(accepted_true), len(accepted_false))):
        if i < len(accepted_true):
            accepted.append(accepted_true[i])
        if i < len(accepted_false):
            accepted.append(accepted_false[i])
    
    # generation_stats を作成（プロンプト統計とパラメータをマージ）
    generation_stats = {
        "generated_true_count": len(accepted_true),
        "generated_false_count": len(accepted_false),
        "dropped_reasons": dropped_reasons,
        "llm_negative_rejected_count": llm_negative_rejected_count,
        "llm_false_generated_count": llm_false_generated_count,
        "mutator_false_generated_count": mutator_false_generated_count,
        "false_source_stats": false_source_stats,
    }
    
    # sample_mutation_log が存在する場合のみ追加
    if sample_mutation_log is not None:
        generation_stats["sample_mutation_log"] = sample_mutation_log
    
    # プロンプト統計を全てマージ（prompt.pyとgenerator.pyで収集した値、LLMパラメータ含む）
    generation_stats.update(prompt_stats)
    
    logger.info(
        f"Quiz生成統計: ○={len(accepted_true)}件, ×={len(accepted_false)}件, dropped={len(rejected)}件, "
        f"llm_input: citations={prompt_stats.get('llm_input_citations_count', 0)}, "
        f"quote_chars={prompt_stats.get('llm_input_total_quote_chars', 0)}, "
        f"prompt_chars={prompt_stats.get('llm_prompt_chars', 0)}, "
        f"output_chars={prompt_stats.get('llm_output_chars', 0)}"
    )
    
    # CHANGED: count=1の場合でも○と×の両方を返す（generation_handler.pyで管理するため）
    # generation_handler.pyで5問生成する場合、各試行で○と×の両方が必要
    # そのため、ここでは○と×の両方を返す（スライスしない）
    logger.info(f"後処理済みクイズ: {len(accepted)}件（○={len(accepted_true)}件, ×={len(accepted_false)}件）")
    
    return (accepted, rejected, attempt_errors, generation_stats)


async def generate_quizzes_with_llm(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
    request_id: str | None = None,
    attempt_index: int | None = None,
    banned_statements: list[str] | None = None,
) -> tuple[list[QuizItemSchema], list[dict], dict]:
    """
    LLMでクイズを生成（3層ガード: Prompt強化 + Robust parse + JSON修復リトライ）
    
    - JSON形式で出力（厳守）
    - 引用に基づくクイズのみ
    - パース失敗時はJSON修復リトライ（1回のみ、同一citations）
    - 途中失敗を attempt_errors に記録
    
    Args:
        level: 難易度
        count: 生成数
        topic: トピック
        citations: 引用リスト
        request_id: リクエストID（Quiz観測用）
        attempt_index: 試行インデックス（Quiz観測用）
        
    Returns:
        (quizzes, attempt_errors, prompt_stats) のタプル
        - quizzes: 生成されたクイズのリスト
        - attempt_errors: 試行ごとの失敗履歴
        - prompt_stats: プロンプト統計情報（LLM負担計測用）
        
    Raises:
        LLMTimeoutError: タイムアウト（最終失敗時のみ）
        LLMInternalError: LLMエラー（最終失敗時のみ）
        ValueError: JSONパースエラー（最終失敗時のみ）
    """
    import time
    
    # LLM出力を正規化する補助関数
    def normalize_llm_output(raw) -> str:
        """LLM出力を必ずstrに正規化"""
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        return str(raw)
    
    # LLMクライアントを取得（設定に応じてOllamaまたはGeminiを選択）
    llm_client = get_llm_client()
    
    # プロンプトを構築（通常生成用）、統計情報も取得
    ret = build_quiz_generation_messages(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
        banned_statements=banned_statements,
    )
    
    # 互換対応: (messages, prompt_stats) または messages のみ
    if isinstance(ret, tuple) and len(ret) == 2:
        messages, prompt_stats = ret
    else:
        messages = ret
        prompt_stats = {}  # 旧仕様の場合は空dict
    
    # prompt_statsが確実に初期化されるよう保険
    if not isinstance(prompt_stats, dict):
        prompt_stats = {}
    
    attempt_errors = []
    
    # Step 1: 通常の生成（1回のみ）
    try:
        t_llm_start = time.perf_counter()
        raw_response = await llm_client.chat(
            messages=messages, 
            is_quiz=True
        )
        t_llm_ms = (time.perf_counter() - t_llm_start) * 1000
        
        # LLM生出力を正規化
        response_text = normalize_llm_output(raw_response)
        
        # LLM生出力を計測（prompt_statsに追加）
        prompt_stats["llm_output_chars"] = len(response_text)
        prompt_stats["llm_output_preview_head"] = response_text[:200]
        
        logger.info(f"LLM生成完了: {len(response_text) if response_text else 0}文字")
        
        # JSONパース（堅牢版、count件に制限）
        t_parse_start = time.perf_counter()
        quizzes, parse_error, raw_excerpt = parse_quiz_json(response_text, citations, count)
        t_parse_ms = (time.perf_counter() - t_parse_start) * 1000
        
        # パース成功の場合
        if parse_error is None and len(quizzes) > 0:
            logger.info(f"Quiz生成成功: {len(quizzes)}件")
            return (quizzes, attempt_errors, prompt_stats)
        
        # パース失敗の場合 → JSON修復リトライへ
        logger.warning(f"JSONパースエラー: {parse_error}")
        
        # attempt_errors に記録
        attempt_errors.append({
            "attempt": 1,
            "stage": "parse",
            "type": parse_error.split(":")[0] if parse_error else "unknown",
            "message": parse_error,
            "t_llm_ms": round(t_llm_ms, 1),
            "t_parse_ms": round(t_parse_ms, 1),
            "raw_excerpt": raw_excerpt,
        })
        
        # Step 2: JSON修復リトライ（1回のみ、同一citations）
        # empty_response または json_parse_error / json_validation_error / json_extraction_error の場合のみ
        if parse_error and ("empty_response" in parse_error or "json_" in parse_error):
            logger.info("JSON修復リトライを開始します（同一citations）")
            
            # JSON修復専用プロンプト
            fix_messages = build_quiz_json_fix_messages(
                level=level,
                count=count,
                topic=topic,
                citations=citations,
                previous_error=parse_error,
            )
            
            try:
                t_fix_llm_start = time.perf_counter()
                raw_fix_response = await llm_client.chat(
                    messages=fix_messages, 
                    is_quiz=True
                )
                t_fix_llm_ms = (time.perf_counter() - t_fix_llm_start) * 1000
                
                # LLM生出力を正規化
                fix_response_text = normalize_llm_output(raw_fix_response)
                
                # LLM生出力を計測（修復版で上書き）
                prompt_stats["llm_output_chars"] = len(fix_response_text)
                prompt_stats["llm_output_preview_head"] = fix_response_text[:200]
                
                logger.info(f"JSON修復LLM完了: {len(fix_response_text)}文字")
                
                # JSONパース（修復版、count件に制限）
                t_fix_parse_start = time.perf_counter()
                fix_quizzes, fix_parse_error, fix_raw_excerpt = parse_quiz_json(fix_response_text, citations, count)
                t_fix_parse_ms = (time.perf_counter() - t_fix_parse_start) * 1000
                
                # 修復成功の場合
                if fix_parse_error is None and len(fix_quizzes) > 0:
                    logger.info(f"JSON修復成功: {len(fix_quizzes)}件")
                    
                    # attempt_errors に修復成功を記録
                    attempt_errors.append({
                        "attempt": 2,
                        "stage": "parse_fix",
                        "type": "success",
                        "message": f"JSON修復成功: {len(fix_quizzes)}件生成",
                        "t_llm_ms": round(t_fix_llm_ms, 1),
                        "t_parse_ms": round(t_fix_parse_ms, 1),
                        "raw_excerpt": fix_raw_excerpt,
                    })
                    
                    return (fix_quizzes, attempt_errors, prompt_stats)
                
                # 修復失敗の場合
                logger.error(f"JSON修復失敗: {fix_parse_error}")
                
                # attempt_errors に修復失敗を記録
                attempt_errors.append({
                    "attempt": 2,
                    "stage": "parse_fix",
                    "type": fix_parse_error.split(":")[0] if fix_parse_error else "unknown",
                    "message": fix_parse_error,
                    "t_llm_ms": round(t_fix_llm_ms, 1),
                    "t_parse_ms": round(t_fix_parse_ms, 1),
                    "raw_excerpt": fix_raw_excerpt,
                })
                
                # 最終失敗として ValueError を投げる
                raise ValueError(f"json_fix_failed: {fix_parse_error}")
            
            except (LLMTimeoutError, LLMInternalError) as e:
                # JSON修復でもLLMエラーが発生
                logger.error(f"JSON修復でLLMエラー: {type(e).__name__}: {e}")
                
                # attempt_errors に記録
                attempt_errors.append({
                    "attempt": 2,
                    "stage": "parse_fix",
                    "type": "llm_error",
                    "message": str(e),
                })
                
                raise  # LLMエラーをそのまま投げる
        
        # 修復対象外のエラー（generated_zero_quizzes など）
        raise ValueError(f"parse_failed: {parse_error}")
    
    except LLMTimeoutError as e:
        logger.error(f"LLMタイムアウト: {e}")
        
        # LLM生出力が取得できていない場合は0を設定
        if "llm_output_chars" not in prompt_stats:
            prompt_stats["llm_output_chars"] = 0
            prompt_stats["llm_output_preview_head"] = ""
        
        # attempt_errors に記録
        attempt_errors.append({
            "attempt": 1,
            "stage": "llm",
            "type": "timeout",
            "message": str(e),
        })
        
        raise  # LLMTimeoutError をそのまま投げる
    
    except LLMInternalError as e:
        logger.error(f"LLM内部エラー: {e}")
        
        # LLM生出力が取得できていない場合は0を設定
        if "llm_output_chars" not in prompt_stats:
            prompt_stats["llm_output_chars"] = 0
            prompt_stats["llm_output_preview_head"] = ""
        
        # attempt_errors に記録
        attempt_errors.append({
            "attempt": 1,
            "stage": "llm",
            "type": "llm_internal_error",
            "message": str(e),
        })
        
        raise  # LLMInternalError をそのまま投げる
    
    except ValueError as e:
        # パースエラーまたは修復失敗
        logger.error(f"最終エラー: {e}")
        
        # LLM生出力が取得できていない場合は0を設定
        if "llm_output_chars" not in prompt_stats:
            prompt_stats["llm_output_chars"] = 0
            prompt_stats["llm_output_preview_head"] = ""
        
        raise
    
    except Exception as e:
        logger.error(f"予期しないエラー: {type(e).__name__}: {e}")
        
        # LLM生出力が取得できていない場合は0を設定
        if "llm_output_chars" not in prompt_stats:
            prompt_stats["llm_output_chars"] = 0
            prompt_stats["llm_output_preview_head"] = ""
        
        # attempt_errors に記録
        attempt_errors.append({
            "attempt": 1,
            "stage": "unknown",
            "type": "unexpected_error",
            "message": f"{type(e).__name__}: {str(e)}",
        })
        
        raise ValueError(f"unexpected_error:{type(e).__name__}:{str(e)}")


def build_search_query(level: str, topic: str | None) -> str:
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
    # levelに応じたキーワード（難易度差を明確に）
    level_keywords = {
        "beginner": "基本 ルール 手順 定義 概要",
        "intermediate": "理由 方法 適用 実務 目的",
        "advanced": "例外 禁止 判断基準 注意 リスク",
    }
    
    level_keyword = level_keywords.get(level, "基本 ルール 手順")
    
    # topicがあればtopicを優先
    if topic:
        return f"{topic} {level_keyword}"
    else:
        return level_keyword
