"""
Judge API用スキーマ（採点のリクエスト・レスポンス型）

【初心者向け】
- JudgeRequest: quiz_id, answer（true=○ / false=×）
- JudgeResponse: is_correct, correct_answer, explanation, citations
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
