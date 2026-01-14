"""
共通スキーマ定義
"""
from pydantic import BaseModel


class Citation(BaseModel):
    """引用情報"""
    source: str
    page: int
    quote: str


class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    error: dict[str, str]
