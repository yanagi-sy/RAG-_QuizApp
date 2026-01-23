"""
LLMによるクイズ生成（オーケストレーション）

LLM呼び出しとバリデーションを統合してクイズを生成する。
"""
import logging

from app.core.settings import settings
from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation
from app.quiz.llm_invocation import generate_quizzes_with_llm
from app.quiz.quiz_validator import validate_and_process_quizzes

# ロガー設定
logger = logging.getLogger(__name__)


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
    accepted_true, accepted_false, rejected, validation_stats = validate_and_process_quizzes(
        raw_quizzes=raw_true_quizzes,
        request_id=request_id,
        attempt_index=attempt_index,
    )
    
    # ○と×を交互に配置（バランス良く）
    accepted = []
    for i in range(max(len(accepted_true), len(accepted_false))):
        if i < len(accepted_true):
            accepted.append(accepted_true[i])
        if i < len(accepted_false):
            accepted.append(accepted_false[i])
    
    # generation_stats を作成（プロンプト統計とパラメータをマージ）
    generation_stats = validation_stats.copy()
    
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
