"""
Judge API用スキーマ
"""
from pydantic import BaseModel, Field

from app.schemas.common import Citation


class JudgeRequest(BaseModel):
    """判定リクエスト"""
    quiz_id: str = Field(..., description="クイズID")
    answer: bool = Field(..., description="回答（true=○、false=×）")


class JudgeResponse(BaseModel):
    """判定レスポンス"""
    is_correct: bool
    correct_answer: bool
    explanation: str
    citations: list[Citation]
