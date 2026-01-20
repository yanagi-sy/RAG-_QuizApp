"""
検索インデックスのキャッシュ管理
"""
import logging
from typing import List, Optional

from app.core.settings import settings
from app.docs.loader import load_documents
from app.docs.chunker import chunk_documents
from app.docs.models import DocumentChunk

# ロガー設定
logger = logging.getLogger(__name__)

# グローバルキャッシュ（in-memory）
_cached_chunks: Optional[List[DocumentChunk]] = None


def build_index() -> List[DocumentChunk]:
    """
    検索インデックスを構築する（chunksを読み込む）

    Returns:
        DocumentChunkのリスト
    """
    # ドキュメントを読み込む
    documents = load_documents(settings.docs_dir)
    
    # チャンクに分割
    chunks = chunk_documents(documents)
    
    logger.info(f"検索インデックス構築完了: {len(chunks)} chunks")
    return chunks


def get_chunks() -> List[DocumentChunk]:
    """
    キャッシュされたchunksを取得する（初回のみ構築）

    Returns:
        DocumentChunkのリスト
    """
    global _cached_chunks
    
    if _cached_chunks is None:
        _cached_chunks = build_index()
    
    return _cached_chunks


def clear_cache() -> None:
    """
    キャッシュをクリアする（テストやリロード時に使用）
    """
    global _cached_chunks
    _cached_chunks = None
    logger.info("検索インデックスキャッシュをクリアしました")
