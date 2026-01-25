"""
検索API用スキーマ（Search のリクエスト・レスポンス型）

【初心者向け】
- SearchRequest: query, k（取得件数）
- SearchResponse: candidates（source, page, snippet, score）
"""
from typing import Optional
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """検索リクエスト"""
    query: str = Field(..., description="検索クエリ")
    k: int = Field(default=5, ge=1, le=10, description="取得件数（1〜10、デフォルト5）")


class Candidate(BaseModel):
    """検索候補"""
    source: str
    page: Optional[int] = None  # PDFならページ番号、txtならnull
    snippet: str  # 表示用の短い抜粋
    score: int  # スコア（大きいほど一致が強い）


class SearchResponse(BaseModel):
    """検索レスポンス"""
    candidates: list[Candidate]
