"""
クイズバリデーションロジック

クイズのバリデーションとfalse_statement生成を担当する。
"""
import logging
import re
import uuid

from app.schemas.quiz import QuizItem as QuizItemSchema
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


def contains_negative_phrase(statement: str) -> bool:
    """
    statement に否定語が含まれているかチェック
    
    Args:
        statement: クイズの statement
        
    Returns:
        True: 否定語が含まれている（×問題の可能性）
        False: 否定語が含まれていない（○問題）
    """
    for pattern in NEGATIVE_PATTERNS:
        if re.search(pattern, statement):
            return True
    return False


def generate_false_statement_with_fallback(original_statement: str) -> tuple[str, str]:
    """
    false_statementを生成（Mutator優先、フォールバック付き）
    
    Args:
        original_statement: 元のstatement（○問題）
        
    Returns:
        (false_statement, source) のタプル
        - false_statement: 生成された×問題のstatement（失敗時は元のstatement）
        - source: 生成元（"mutator" または "fallback" または "none"）
    """
    # Mutatorで生成
    false_statement = make_false_statement(original_statement)
    source = "mutator"
    
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
        
        for pattern, replacement in alternative_patterns:
            if re.search(pattern, original_statement):
                false_statement = re.sub(pattern, replacement, original_statement)
                if false_statement != original_statement:
                    logger.info(f"代替方法で×問題を生成: パターン '{pattern}' を適用")
                    source = "fallback"
                    break
        
        # 代替方法2: "必ず"を削除して「行わなくてもよい」に変換
        if false_statement == original_statement and "必ず" in original_statement:
            false_statement = original_statement.replace("必ず", "").replace("  ", " ").strip()
            if false_statement != original_statement:
                logger.info("代替方法で×問題を生成: '必ず'を削除")
                source = "fallback"
        
        # 代替方法3: "必須"を"任意"に変換
        if false_statement == original_statement and "必須" in original_statement:
            false_statement = original_statement.replace("必須", "任意")
            if false_statement != original_statement:
                logger.info("代替方法で×問題を生成: '必須'を'任意'に変換")
                source = "fallback"
        
        # 代替方法4: "必要"を"不要"に変換
        if false_statement == original_statement and "必要" in original_statement:
            false_statement = original_statement.replace("必要", "不要")
            if false_statement != original_statement:
                logger.info("代替方法で×問題を生成: '必要'を'不要'に変換")
                source = "fallback"
    
    # すべての方法が失敗した場合
    if false_statement == original_statement:
        source = "none"
    
    return false_statement, source


def validate_and_process_quizzes(
    raw_quizzes: list[QuizItemSchema],
    request_id: str | None = None,
    attempt_index: int | None = None,
) -> tuple[list[QuizItemSchema], list[QuizItemSchema], list[dict], dict]:
    """
    クイズをバリデーションし、○と×を生成する
    
    Args:
        raw_quizzes: LLMから生成された生のクイズリスト
        request_id: リクエストID（ログ用）
        attempt_index: 試行インデックス（ログ用）
        
    Returns:
        (accepted_true, accepted_false, rejected, generation_stats) のタプル
        - accepted_true: 採用された○問題のリスト
        - accepted_false: 採用された×問題のリスト
        - rejected: 不合格アイテム情報のリスト
        - generation_stats: 生成統計情報
    """
    accepted_true = []  # 採用された○
    accepted_false = []  # 採用された×
    rejected = []  # 不合格アイテム
    dropped_reasons = {}  # reason -> count の集計
    llm_negative_rejected_count = 0  # LLM由来の否定文reject数
    llm_false_generated_count = 0  # LLM由来の×生成数
    mutator_false_generated_count = 0  # mutator由来の×生成数
    fallback_false_generated_count = 0  # fallback由来の×生成数
    sample_mutation_log = None  # true->false の例
    false_source_stats = {"llm": 0, "mutator": 0, "fallback": 0, "none": 0}  # false_statement生成元の統計
    
    for quiz in raw_quizzes:
        # 後処理を先に実行（statement正規化、explanation固定、citations選別）
        try:
            processed_quiz = postprocess_quiz_item(quiz)
        except Exception as e:
            logger.warning(f"後処理失敗: {e}、元のクイズを使用")
            processed_quiz = quiz
        
        # dict に変換してバリデーション（○）
        quiz_dict = processed_quiz.model_dump() if hasattr(processed_quiz, "model_dump") else processed_quiz.dict()
        statement = quiz_dict.get("statement", "")
        
        # 否定語チェック（LLMが勝手に×を作るのを防ぐ）
        if contains_negative_phrase(statement):
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
                request_id_str = str(request_id) if request_id is not None else "None"
                attempt_index_str = str(attempt_index) if attempt_index is not None else "None"
                logger.info(
                    f"[PIPE:BEFORE_MUTATOR] "
                    f"request_id={request_id_str}, attempt_index={attempt_index_str}, "
                    f"statement_preview={original_statement[:120]}, "
                    f"statement_len={len(original_statement)}"
                )
                
                # Mutatorで生成（フォールバック付き）
                false_statement, false_source = generate_false_statement_with_fallback(original_statement)
            
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
                    elif false_source == "fallback":
                        fallback_false_generated_count += 1
                        false_source_stats["fallback"] += 1
                    
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
    
    # generation_stats を作成
    generation_stats = {
        "generated_true_count": len(accepted_true),
        "generated_false_count": len(accepted_false),
        "dropped_reasons": dropped_reasons,
        "llm_negative_rejected_count": llm_negative_rejected_count,
        "llm_false_generated_count": llm_false_generated_count,
        "mutator_false_generated_count": mutator_false_generated_count,
        "fallback_false_generated_count": fallback_false_generated_count,
        "false_source_stats": false_source_stats,
    }
    
    # sample_mutation_log が存在する場合のみ追加
    if sample_mutation_log is not None:
        generation_stats["sample_mutation_log"] = sample_mutation_log
    
    logger.info(
        f"Quizバリデーション統計: ○={len(accepted_true)}件, ×={len(accepted_false)}件, dropped={len(rejected)}件"
    )
    
    return (accepted_true, accepted_false, rejected, generation_stats)
