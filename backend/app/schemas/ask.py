"""
QA (Ask) API用スキーマ
"""
from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.common import Citation


class RetrievalParams(BaseModel):
    """検索方法パラメータ"""
    semantic: float = Field(..., description="意味検索の重み（0.0-1.0）")
    keyword: float = Field(..., description="キーワード検索の重み（0.0-1.0）")


class AskRequest(BaseModel):
    """質問リクエスト"""
    question: str = Field(..., description="質問文")
    retrieval: Optional[RetrievalParams] = Field(None, description="検索方法のパラメータ")


class AskResponse(BaseModel):
    """質問レスポンス"""
    answer: str
    citations: list[Citation]
