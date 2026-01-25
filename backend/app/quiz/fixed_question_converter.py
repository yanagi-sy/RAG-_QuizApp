"""
固定問題変換ロジック

【初心者向け】
- 4問目と5問目を×問題に固定する機能
- ○問題を×問題に変換する際、複数の代替方法を試行
"""
import logging
import re
import uuid

from app.schemas.quiz import QuizItem as QuizItemSchema
from app.quiz.mutator import make_false_statement

# ロガー設定
logger = logging.getLogger(__name__)


def _convert_to_false_statement_with_fallback(original_statement: str) -> str:
    """
    ○問題を×問題に変換（複数の代替方法を試行）
    
    Args:
        original_statement: 元の○問題のstatement
        
    Returns:
        変換された×問題のstatement
    """
    false_statement = make_false_statement(original_statement)
    
    # Mutatorが失敗した場合（元の文と同じ）、代替方法を試す
    if false_statement == original_statement:
        logger.info(f"[FIXED_QUESTION] Mutatorが失敗したため、代替方法を試行します: '{original_statement[:50]}...'")
        
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
            (r"対処する。$", "対処しない。"),
            (r"示す。$", "示さない。"),
            (r"持つ。$", "持たない。"),
            (r"着用する。$", "着用しない。"),
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
                    logger.info(f"[FIXED_QUESTION] 代替方法で×問題を生成: パターン '{pattern}' を適用")
                    break
        
        # 代替方法2: "必ず"を削除して「行わなくてもよい」に変換
        if false_statement == original_statement and "必ず" in original_statement:
            false_statement = original_statement.replace("必ず", "").replace("  ", " ").strip()
            if false_statement != original_statement:
                logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '必ず'を削除")
        
        # 代替方法3: "必須"を"任意"に変換
        if false_statement == original_statement and "必須" in original_statement:
            false_statement = original_statement.replace("必須", "任意")
            if false_statement != original_statement:
                logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '必須'を'任意'に変換")
        
        # 代替方法4: "必要"を"不要"に変換
        if false_statement == original_statement and "必要" in original_statement:
            false_statement = original_statement.replace("必要", "不要")
            if false_statement != original_statement:
                logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '必要'を'不要'に変換")
        
        # 代替方法5: それでも失敗した場合、文頭に「誤り：」を追加（最後の手段）
        if false_statement == original_statement:
            false_statement = f"誤り：{original_statement}"
            logger.warning(f"[FIXED_QUESTION] すべての代替方法が失敗したため、文頭に「誤り：」を追加: '{false_statement[:50]}...'")
    
    return false_statement


def convert_quiz_to_false(quiz: QuizItemSchema, question_index: int) -> QuizItemSchema:
    """
    クイズを×問題に変換
    
    Args:
        quiz: 変換対象のクイズ（○問題）
        question_index: 問題のインデックス（4問目=3, 5問目=4）
        
    Returns:
        変換された×問題のクイズ
    """
    # 元のstatementが○問題であることを確認（念のため）
    if not quiz.answer_bool:
        logger.info(f"[FIXED_QUESTION] {question_index+1}問目は既に×問題です: '{quiz.statement[:50]}...'")
        return quiz
    
    original_statement = quiz.statement
    false_statement = _convert_to_false_statement_with_fallback(original_statement)
    
    # ×問題に変換（新しいIDを生成）
    false_quiz_dict = quiz.model_dump() if hasattr(quiz, "model_dump") else quiz.dict()
    false_quiz_dict["id"] = str(uuid.uuid4())[:8]
    false_quiz_dict["statement"] = false_statement
    false_quiz_dict["answer_bool"] = False
    false_quiz_dict["explanation"] = f"この文は誤りです。正しくは「{original_statement}」です。{quiz.explanation}"
    
    # QuizItemSchemaに変換して返す
    converted_quiz = QuizItemSchema(**false_quiz_dict)
    logger.info(f"[FIXED_QUESTION] {question_index+1}問目を×問題に固定: '{original_statement[:50]}...' -> '{false_statement[:50]}...'")
    
    return converted_quiz


def apply_fixed_questions(accepted_quizzes: list[QuizItemSchema]) -> list[QuizItemSchema]:
    """
    4問目と5問目を×問題に固定
    
    【固定ルール】4問目と5問目を×問題に固定
    - 4問目（インデックス3）と5問目（インデックス4）が存在する場合、×問題に変換
    
    Args:
        accepted_quizzes: 採用されたクイズのリスト
        
    Returns:
        固定問題を適用したクイズのリスト
    """
    result = list(accepted_quizzes)  # コピーを作成
    
    # 4問目を×問題に変換（インデックス3）
    if len(result) > 3:
        result[3] = convert_quiz_to_false(result[3], 3)
    
    # 5問目を×問題に変換（インデックス4）
    if len(result) > 4:
        result[4] = convert_quiz_to_false(result[4], 4)
    
    return result
