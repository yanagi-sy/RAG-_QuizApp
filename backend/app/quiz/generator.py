"""
LLMによるクイズ生成
"""
import asyncio
import json
import logging
import uuid

from app.core.settings import settings
from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.llm.base import LLMInternalError, LLMTimeoutError
from app.llm.ollama import get_ollama_client
from app.llm.prompt import build_quiz_generation_messages, build_quiz_json_fix_messages
from app.quiz.parser import parse_quiz_json
from app.quiz.validator import validate_quiz_item
from app.quiz.mutator import make_false_statement

# ロガー設定
logger = logging.getLogger(__name__)


async def generate_and_validate_quizzes(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
) -> tuple[list[QuizItemSchema], list[dict], list[dict], dict]:
    """
    LLMでクイズを生成し、バリデーションを行う（○のみ生成 → ×はmutatorで生成）
    
    戦略:
    1. LLMに count 件の「正しい断言文（○）」を生成させる
    2. 各 item を validator でチェックし、合格したものを採用
    3. 採用した各 item から、mutator で「×」を生成
    4. ×もvalidatorでチェックし、合格したものを採用
    5. 最終的に count 件（○と×の組み合わせ）を揃える
    
    Args:
        level: 難易度
        count: 生成数
        topic: トピック
        citations: 引用リスト
        
    Returns:
        (accepted_quizzes, rejected_items, attempt_errors, generation_stats) のタプル
        - accepted_quizzes: バリデーション通過したクイズのリスト
        - rejected_items: バリデーション失敗したアイテム情報のリスト
        - attempt_errors: 試行ごとの失敗履歴（途中失敗を含む）
        - generation_stats: 生成統計（generated_true_count, generated_false_count, dropped_reasons）
    """
    # settings をインポート（LLMパラメータ取得用）
    from app.core.settings import settings
    from app.llm.prompt import build_quiz_generation_messages
    
    # prompt_statsを先に取得（エラー時も保持するため）
    ret = build_quiz_generation_messages(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
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
    
    # バリデーション & mutator で○→×を生成
    accepted_true = []  # 採用された○
    accepted_false = []  # 採用された×
    rejected = []  # 不合格アイテム
    dropped_reasons = {}  # reason -> count の集計
    
    for quiz in raw_true_quizzes:
        # dict に変換してバリデーション（○）
        quiz_dict = quiz.model_dump() if hasattr(quiz, "model_dump") else quiz.dict()
        ok, reason = validate_quiz_item(quiz_dict)
        
        if ok:
            # ○として採用
            accepted_true.append(quiz)
            
            # ×を生成（mutator）
            false_statement = make_false_statement(quiz_dict["statement"])
            
            # ×がvalidatorを通過するかチェック
            false_quiz_dict = quiz_dict.copy()
            false_quiz_dict["id"] = str(uuid.uuid4())[:8]  # 新しいIDを生成
            false_quiz_dict["statement"] = false_statement
            false_quiz_dict["answer_bool"] = False
            
            # validator チェック（×）
            ok_false, reason_false = validate_quiz_item(false_quiz_dict)
            
            if ok_false and false_statement != quiz_dict["statement"]:
                # ×として採用
                false_quiz = QuizItemSchema(**false_quiz_dict)
                accepted_false.append(false_quiz)
            else:
                # ×が不合格
                logger.warning(f"False quiz バリデーション失敗: {reason_false}")
                rejected.append({
                    "statement": false_statement[:100],
                    "reason": f"false:{reason_false}",
                })
                # dropped_reasons に集計
                dropped_key = f"false:{reason_false}"
                dropped_reasons[dropped_key] = dropped_reasons.get(dropped_key, 0) + 1
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
    }
    
    # プロンプト統計を全てマージ（prompt.pyとgenerator.pyで収集した値、LLMパラメータ含む）
    generation_stats.update(prompt_stats)
    
    logger.info(
        f"Quiz生成統計: ○={len(accepted_true)}件, ×={len(accepted_false)}件, dropped={len(rejected)}件, "
        f"llm_input: citations={prompt_stats.get('llm_input_citations_count', 0)}, "
        f"quote_chars={prompt_stats.get('llm_input_total_quote_chars', 0)}, "
        f"prompt_chars={prompt_stats.get('llm_prompt_chars', 0)}, "
        f"output_chars={prompt_stats.get('llm_output_chars', 0)}"
    )
    
    return (accepted, rejected, attempt_errors, generation_stats)


async def generate_quizzes_with_llm(
    level: str,
    count: int,
    topic: str | None,
    citations: list[Citation],
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
    
    # LLMクライアントを取得
    llm_client = get_ollama_client()
    
    # プロンプトを構築（通常生成用）、統計情報も取得
    ret = build_quiz_generation_messages(
        level=level,
        count=count,
        topic=topic,
        citations=citations,
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
        raw_response = await llm_client.chat(messages=messages, is_quiz=True)
        t_llm_ms = (time.perf_counter() - t_llm_start) * 1000
        
        # LLM生出力を正規化
        response_text = normalize_llm_output(raw_response)
        
        # LLM生出力を計測（prompt_statsに追加）
        prompt_stats["llm_output_chars"] = len(response_text)
        prompt_stats["llm_output_preview_head"] = response_text[:200]
        
        logger.info(f"LLM生成完了: {len(response_text) if response_text else 0}文字")
        
        # JSONパース（堅牢版）
        t_parse_start = time.perf_counter()
        quizzes, parse_error, raw_excerpt = parse_quiz_json(response_text, citations)
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
                raw_fix_response = await llm_client.chat(messages=fix_messages, is_quiz=True)
                t_fix_llm_ms = (time.perf_counter() - t_fix_llm_start) * 1000
                
                # LLM生出力を正規化
                fix_response_text = normalize_llm_output(raw_fix_response)
                
                # LLM生出力を計測（修復版で上書き）
                prompt_stats["llm_output_chars"] = len(fix_response_text)
                prompt_stats["llm_output_preview_head"] = fix_response_text[:200]
                
                logger.info(f"JSON修復LLM完了: {len(fix_response_text)}文字")
                
                # JSONパース（修復版）
                t_fix_parse_start = time.perf_counter()
                fix_quizzes, fix_parse_error, fix_raw_excerpt = parse_quiz_json(fix_response_text, citations)
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
