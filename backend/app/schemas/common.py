"""
共通スキーマ定義（APIで共通利用する型）

【初心者向け】
- Citation: 引用（source / page / quote）。QA・Quiz の根拠表示に使用
- SourceInfo: 資料一覧用（id / title / source / type）
"""
from pydantic import BaseModel


class Citation(BaseModel):
    """引用情報"""
    source: str
    page: int | None  # PDFならページ番号、txtならnull
    quote: str


class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    error: dict[str, str]
