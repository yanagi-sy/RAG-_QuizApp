"""
LLM呼び出しロジック

LLMでクイズを生成する処理を担当する。
"""
import logging
import time

from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.llm.base import LLMInternalError, LLMTimeoutError
from app.llm.ollama import get_ollama_client
from app.llm.prompt import build_quiz_generation_messages, build_quiz_json_fix_messages
from app.quiz.parser import parse_quiz_json

# ロガー設定
logger = logging.getLogger(__name__)


def normalize_llm_output(raw) -> str:
    """
    LLM出力を必ずstrに正規化
    
    Args:
        raw: LLMの生出力
        
    Returns:
        正規化された文字列
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(raw)


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
    # LLMクライアントを取得
    llm_client = get_ollama_client()
    
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
