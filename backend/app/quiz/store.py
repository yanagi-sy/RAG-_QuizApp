"""
Quiz用in-memoryストア
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from app.schemas.common import Citation


@dataclass
class QuizItem:
    """クイズアイテム"""
    question: str
    correct_answer: bool
    explanation: str
    citations: list[Citation]


# in-memoryストア（キー：quiz_id、値：QuizItem）
_quiz_store: dict[str, QuizItem] = {}


def save_quiz(item: QuizItem) -> str:
    """
    クイズを保存してquiz_idを返す
    
    Args:
        item: クイズアイテム
        
    Returns:
        quiz_id: UUID文字列
    """
    quiz_id = str(uuid.uuid4())
    _quiz_store[quiz_id] = item
    return quiz_id


def get_quiz(quiz_id: str) -> Optional[QuizItem]:
    """
    クイズを取得する
    
    Args:
        quiz_id: クイズID
        
    Returns:
        QuizItem または None
    """
    return _quiz_store.get(quiz_id)


def clear_all() -> None:
    """すべてのクイズをクリアする（テスト用）"""
    _quiz_store.clear()
