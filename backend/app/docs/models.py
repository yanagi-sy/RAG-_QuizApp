"""
ドキュメント関連の型定義
"""
from dataclasses import dataclass


@dataclass
class Document:
    """ドキュメント（ファイル単位）"""
    source: str  # ファイル名
    page: int  # PDFならページ番号、txtは1固定
    text: str  # 抽出テキスト


@dataclass
class DocumentChunk:
    """ドキュメントチャンク"""
    source: str  # ファイル名
    page: int  # ページ番号
    chunk_index: int  # チャンクのインデックス（0始まり）
    text: str  # チャンクのテキスト
