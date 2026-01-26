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
    
    【初心者向け】
    4問目と5問目を×問題に固定するため、○問題を×問題に変換します。
    変換には複数の方法を試行し、どれか1つでも成功すれば変換された文を返します。
    
    処理の流れ:
    1. mutatorモジュールのmake_false_statementを試行（基本的な変換ルール）
    2. 失敗した場合、代替方法1: 文末の否定化（例: "行う。" → "行わない。"）
    3. 失敗した場合、代替方法2: "必ず"を削除
    4. 失敗した場合、代替方法3: "必須"を"任意"に変換
    5. 失敗した場合、代替方法4: "必要"を"不要"に変換
    6. すべて失敗した場合、代替方法5: 文頭に「誤り：」を追加（最後の手段）
    
    【重要】変換後の文が元の文と異なることを必ず確認します。
    同じ場合は、必ず誤った内容になるように強制的に変換します。
    
    Args:
        original_statement: 元の○問題のstatement（正しい断言文）
        
    Returns:
        変換された×問題のstatement（誤った断言文、必ず元の文と異なる）
        
    Example:
        "地震時は身を守る行動をとる。" → "地震時は身を守る行動をとらない。"
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
            # より多くのパターンを追加
            (r"行う$", "行わない"),
            (r"確認する$", "確認しない"),
            (r"連絡する$", "連絡しない"),
            (r"報告する$", "報告しない"),
            (r"実施する$", "実施しない"),
            (r"実行する$", "実行しない"),
            (r"処理する$", "処理しない"),
            (r"対応する$", "対応しない"),
            (r"対処する$", "対処しない"),
            (r"示す$", "示さない"),
            (r"持つ$", "持たない"),
            (r"着用する$", "着用しない"),
            (r"である$", "ではない"),
            (r"する$", "しない"),
            (r"できる$", "できない"),
            (r"される$", "されない"),
            (r"ある$", "ない"),
        ]
        
        for pattern, replacement in alternative_patterns:
            if re.search(pattern, original_statement):
                false_statement = re.sub(pattern, replacement, original_statement)
                if false_statement != original_statement:
                    logger.info(f"[FIXED_QUESTION] 代替方法で×問題を生成: パターン '{pattern}' を適用")
                    break
        
        # 代替方法1-2: 文中の動詞も否定化（「疑う：」など）
        if false_statement == original_statement:
            verb_negation_patterns = [
                ("疑う：", "疑わない："),
                ("疑う:", "疑わない:"),
                ("確認する", "確認しない"),
                ("連絡する", "連絡しない"),
                ("報告する", "報告しない"),
                ("実施する", "実施しない"),
                ("実行する", "実行しない"),
                ("処理する", "処理しない"),
                ("対応する", "対応しない"),
                ("対処する", "対処しない"),
                ("示す", "示さない"),
                ("持つ", "持たない"),
                ("着用する", "着用しない"),
                ("行う", "行わない"),
            ]
            for verb, negated_verb in verb_negation_patterns:
                if verb in original_statement:
                    false_statement = original_statement.replace(verb, negated_verb, 1)  # 最初の1回だけ置換
                    if false_statement != original_statement:
                        logger.info(f"[FIXED_QUESTION] 代替方法で×問題を生成: '{verb}'を'{negated_verb}'に変換")
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
        
        # 代替方法5: より積極的な否定化パターン
        if false_statement == original_statement:
            # "〜する必要がある" → "〜する必要がない"
            if "必要がある" in original_statement:
                false_statement = original_statement.replace("必要がある", "必要がない")
                if false_statement != original_statement:
                    logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '必要がある'を'必要がない'に変換")
        
        if false_statement == original_statement:
            # "〜しなければならない" → "〜しなくてもよい"
            if "しなければならない" in original_statement:
                false_statement = original_statement.replace("しなければならない", "しなくてもよい")
                if false_statement != original_statement:
                    logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: 'しなければならない'を'しなくてもよい'に変換")
        
        if false_statement == original_statement:
            # "〜すべき" → "〜すべきではない"
            if "すべき" in original_statement and "すべきではない" not in original_statement:
                false_statement = original_statement.replace("すべき", "すべきではない")
                if false_statement != original_statement:
                    logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: 'すべき'を'すべきではない'に変換")
        
        # 代替方法6: リスト形式の文の場合、一部の項目を削除または変更
        if false_statement == original_statement:
            # 「：」で区切られたリスト形式の場合
            if "：" in original_statement or ":" in original_statement:
                # 「疑う：」→「疑わない：」に変換
                if "疑う：" in original_statement:
                    false_statement = original_statement.replace("疑う：", "疑わない：")
                    if false_statement != original_statement:
                        logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '疑う：'を'疑わない：'に変換")
                elif "疑う:" in original_statement:
                    false_statement = original_statement.replace("疑う:", "疑わない:")
                    if false_statement != original_statement:
                        logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '疑う:'を'疑わない:'に変換")
                # リストの一部を削除（最後の項目を削除）
                elif "、" in original_statement:
                    parts = original_statement.split("、")
                    if len(parts) > 1:
                        # 最後の項目を削除
                        false_statement = "、".join(parts[:-1]) + "。"
                        if false_statement != original_statement:
                            logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: リストの最後の項目を削除")
        
        # 代替方法7: それでも失敗した場合、文の内容を変更する
        if false_statement == original_statement:
            # 「優先的に」→「優先的には」に変更（意味を変える）
            if "優先的に" in original_statement:
                false_statement = original_statement.replace("優先的に", "優先的には")
                if false_statement != original_statement:
                    logger.info("[FIXED_QUESTION] 代替方法で×問題を生成: '優先的に'を'優先的には'に変換")
        
        # 代替方法8: それでも失敗した場合、文頭に「誤り：」を追加（最後の手段）
        # ただし、この場合は文の内容自体も変更する必要がある
        if false_statement == original_statement:
            # 「誤り：」を追加するだけでなく、文の内容も変更する
            # 例: 「疑う」→「疑わない」に変更
            modified_statement = original_statement
            if "疑う" in modified_statement:
                modified_statement = modified_statement.replace("疑う", "疑わない")
            elif "行う" in modified_statement:
                modified_statement = modified_statement.replace("行う", "行わない")
            elif "確認する" in modified_statement:
                modified_statement = modified_statement.replace("確認する", "確認しない")
            elif "連絡する" in modified_statement:
                modified_statement = modified_statement.replace("連絡する", "連絡しない")
            elif "報告する" in modified_statement:
                modified_statement = modified_statement.replace("報告する", "報告しない")
            
            # 内容が変更された場合はそれを使用、変更されなかった場合は「誤り：」を追加
            if modified_statement != original_statement:
                false_statement = modified_statement
                logger.info(f"[FIXED_QUESTION] 代替方法で×問題を生成: 文の内容を変更: '{original_statement[:50]}...' -> '{false_statement[:50]}...'")
            else:
                false_statement = f"誤り：{original_statement}"
                logger.warning(f"[FIXED_QUESTION] すべての代替方法が失敗したため、文頭に「誤り：」を追加: '{false_statement[:50]}...'")
    
    # 【重要】最終チェック: 変換後の文が元の文と異なることを確認
    # 同じ場合は、必ず誤った内容になるように強制的に変換
    if false_statement == original_statement:
        # 強制的に誤った文を生成（文頭に「誤り：」を追加）
        false_statement = f"誤り：{original_statement}"
        logger.error(
            f"[FIXED_QUESTION] 変換が完全に失敗したため、強制的に「誤り：」を追加: "
            f"'{original_statement[:50]}...' -> '{false_statement[:50]}...'"
        )
    
    # 変換後の文が元の文と異なることを最終確認
    if false_statement == original_statement:
        # それでも同じ場合は、文末に「（誤り）」を追加
        false_statement = f"{original_statement}（誤り）"
        logger.error(
            f"[FIXED_QUESTION] 最終手段: 文末に「（誤り）」を追加: "
            f"'{original_statement[:50]}...' -> '{false_statement[:50]}...'"
        )
    
    return false_statement


def convert_quiz_to_false(quiz: QuizItemSchema, question_index: int) -> QuizItemSchema:
    """
    クイズを×問題に変換
    
    【初心者向け】
    ○問題（正しい断言文）を×問題（誤った断言文）に変換します。
    変換には複数の方法を試行し、どれか1つでも成功すれば変換されたクイズを返します。
    
    処理の流れ:
    1. 元のクイズが○問題（answer_bool=True）か確認
    2. 既に×問題の場合はそのまま返す
    3. ○問題の場合、_convert_to_false_statement_with_fallbackで×問題に変換
    4. 新しいIDを生成し、explanationを更新（「この文は誤りです。正しくは...」）
    
    Args:
        quiz: 変換対象のクイズ（○問題、answer_bool=True）
        question_index: 問題のインデックス（4問目=3, 5問目=4、0始まり）
        
    Returns:
        変換された×問題のクイズ（answer_bool=False、新しいID、更新されたexplanation）
    """
    # 元のstatementが○問題であることを確認（念のため）
    if not quiz.answer_bool:
        logger.info(f"[FIXED_QUESTION] {question_index+1}問目は既に×問題です: '{quiz.statement[:50]}...'")
        return quiz
    
    original_statement = quiz.statement
    false_statement = _convert_to_false_statement_with_fallback(original_statement)
    
    # 【重要】変換後の文が元の文と異なることを最終確認
    # 同じ場合は、必ず誤った内容になるように強制的に変換
    if false_statement == original_statement:
        # 強制的に誤った文を生成（文頭に「誤り：」を追加）
        false_statement = f"誤り：{original_statement}"
        logger.error(
            f"[FIXED_QUESTION] convert_quiz_to_false: 変換が完全に失敗したため、強制的に「誤り：」を追加: "
            f"'{original_statement[:50]}...' -> '{false_statement[:50]}...'"
        )
    
    # ×問題に変換（新しいIDを生成）
    false_quiz_dict = quiz.model_dump() if hasattr(quiz, "model_dump") else quiz.dict()
    false_quiz_dict["id"] = str(uuid.uuid4())[:8]
    false_quiz_dict["statement"] = false_statement
    false_quiz_dict["answer_bool"] = False
    false_quiz_dict["explanation"] = f"この文は誤りです。正しくは「{original_statement}」です。{quiz.explanation}"
    
    # 【最終確認】変換後のstatementが元のstatementと異なることを確認
    if false_quiz_dict["statement"] == original_statement:
        logger.error(
            f"[FIXED_QUESTION] 重大なエラー: 変換後のstatementが元のstatementと同じです。"
            f"question_index={question_index}, original='{original_statement[:50]}...'"
        )
        # それでも同じ場合は、文末に「（誤り）」を追加
        false_quiz_dict["statement"] = f"{original_statement}（誤り）"
    
    # QuizItemSchemaに変換して返す
    converted_quiz = QuizItemSchema(**false_quiz_dict)
    logger.info(
        f"[FIXED_QUESTION] {question_index+1}問目を×問題に固定: "
        f"'{original_statement[:50]}...' -> '{converted_quiz.statement[:50]}...' "
        f"(answer_bool={converted_quiz.answer_bool})"
    )
    
    return converted_quiz


def apply_fixed_questions(accepted_quizzes: list[QuizItemSchema]) -> list[QuizItemSchema]:
    """
    4問目と5問目を×問題に固定
    
    【初心者向け】
    クイズセットに必ず×問題が含まれるようにするため、4問目と5問目を×問題に固定します。
    これにより、ユーザーは○問題だけでなく×問題も解くことができ、学習効果が向上します。
    
    【固定ルール】
    - 4問目（インデックス3）が存在する場合、×問題に変換
    - 5問目（インデックス4）が存在する場合、×問題に変換
    - 既に×問題の場合はそのまま（変換しない）
    
    処理の流れ:
    1. accepted_quizzesのコピーを作成（元のリストを変更しない）
    2. 4問目（インデックス3）が存在する場合、convert_quiz_to_falseで変換
    3. 5問目（インデックス4）が存在する場合、convert_quiz_to_falseで変換
    4. 変換後のリストを返す
    
    Args:
        accepted_quizzes: 採用されたクイズのリスト（○問題のみ、または○と×の混在）
        
    Returns:
        固定問題を適用したクイズのリスト（4問目と5問目が×問題に変換されている）
    """
    result = list(accepted_quizzes)  # コピーを作成
    
    # 4問目を×問題に変換（インデックス3）
    if len(result) > 3:
        result[3] = convert_quiz_to_false(result[3], 3)
    
    # 5問目を×問題に変換（インデックス4）
    if len(result) > 4:
        result[4] = convert_quiz_to_false(result[4], 4)
    
    return result
