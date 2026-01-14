"""
Quiz API用スキーマ
"""
from typing import Literal
from pydantic import BaseModel, Field

Level = Literal["beginner", "intermediate", "advanced"]


class QuizRequest(BaseModel):
    """クイズ出題リクエスト"""
    level: Level = Field(..., description="難易度")


class QuizResponse(BaseModel):
    """クイズ出題レスポンス"""
    quiz_id: str
    question: str
