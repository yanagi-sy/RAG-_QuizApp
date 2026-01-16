"""
QA (Ask) API用スキーマ
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.schemas.common import Citation


class RetrievalParams(BaseModel):
    """検索方法パラメータ"""
    semantic_weight: float = Field(
        default=0.7,  # CHANGED: デフォルト0.7に変更
        ge=0.0,
        le=1.0,
        description="意味検索の重み（0.0-1.0）。keyword_weight = 1 - semantic_weight"
    )


class AskRequest(BaseModel):
    """質問リクエスト"""
    question: str = Field(..., description="質問文")
    retrieval: Optional[RetrievalParams] = Field(None, description="検索方法のパラメータ")
    debug: bool = Field(default=False, description="NEW: デバッグ情報を返すかどうか")


class AskResponse(BaseModel):
    """質問レスポンス"""
    answer: str
    citations: list[Citation]
    debug: Optional[Dict[str, Any]] = Field(default=None, description="NEW: デバッグ情報（debug=trueの場合のみ）")
