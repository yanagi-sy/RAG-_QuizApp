"""
Quizアイテムの後処理

statement正規化、explanation固定、citations選別を行う。
"""
import logging
import re

from app.schemas.quiz import QuizItem as QuizItemSchema
from app.schemas.common import Citation

# ロガー設定
logger = logging.getLogger(__name__)


def postprocess_quiz_item(quiz: QuizItemSchema) -> QuizItemSchema:
    """
    Quizアイテムの後処理
    
    - statement正規化（【source】等のメタ情報除去）
    - explanation固定（既にLLMで生成済みの場合はそのまま）
    - citations選別（重複排除、最大件数制限）
    
    Args:
        quiz: 元のQuizアイテム
        
    Returns:
        後処理済みのQuizアイテム
    """
    # statement正規化
    statement = quiz.statement
    
    # 【source】等のメタ情報を除去
    statement = re.sub(r'【[^】]+】', '', statement)
    statement = re.sub(r'\[[^\]]+\]', '', statement)
    
    # 前後の空白を削除
    statement = statement.strip()
    
    # explanationはそのまま（LLMで生成済み）
    explanation = quiz.explanation
    
    # citations選別（重複排除、最大件数制限）
    citations = _deduplicate_citations(quiz.citations)
    
    # 最大5件に制限
    citations = citations[:5]
    
    # 新しいQuizアイテムを作成
    processed_quiz = QuizItemSchema(
        id=quiz.id,
        statement=statement,
        type=quiz.type,
        answer_bool=quiz.answer_bool,
        explanation=explanation,
        citations=citations,
    )
    
    return processed_quiz


def _deduplicate_citations(citations: list[Citation]) -> list[Citation]:
    """
    citationsの重複排除
    
    Args:
        citations: 引用リスト
        
    Returns:
        重複排除済みの引用リスト
    """
    seen = set()
    deduplicated = []
    
    for citation in citations:
        # source, page, quote先頭60文字で重複判定
        key = (
            citation.source,
            citation.page,
            citation.quote[:60] if citation.quote else ""
        )
        
        if key not in seen:
            seen.add(key)
            deduplicated.append(citation)
    
    return deduplicated
