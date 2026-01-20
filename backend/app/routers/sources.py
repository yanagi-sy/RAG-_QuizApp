"""
Sources APIルーター

検索対象の資料一覧を取得するエンドポイント
"""
from fastapi import APIRouter
from typing import List
from pathlib import Path
import logging

from app.schemas.common import SourceInfo
from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=List[SourceInfo])
async def get_sources() -> List[SourceInfo]:
    """
    資料一覧を Chroma から取得
    
    Chroma の metadata.source をユニーク収集して返す
    
    Returns:
        資料情報のリスト
    """
    try:
        collection = get_vectorstore(settings.chroma_dir)
        
        # 全メタデータを取得（limit を大きく設定）
        results = collection.get(
            include=["metadatas"],
            limit=10000  # 十分大きな値
        )
        
        metadatas = results.get("metadatas", [])
        
        # source をユニーク収集
        sources_set = set()
        for metadata in metadatas:
            if metadata and "source" in metadata:
                sources_set.add(metadata["source"])
        
        # SourceInfo に変換
        source_infos = []
        for source in sorted(sources_set):
            # 拡張子判定
            source_lower = source.lower()
            if source_lower.endswith(".pdf"):
                file_type = "pdf"
            elif source_lower.endswith(".txt"):
                file_type = "txt"
            else:
                file_type = "other"
            
            # タイトルは拡張子を除いたファイル名
            title = Path(source).stem
            
            source_infos.append(
                SourceInfo(
                    id=source,  # id = source（完全一致）
                    title=title,
                    source=source,
                    type=file_type,
                )
            )
        
        logger.info(f"Chromaから資料一覧を取得: {len(source_infos)}件")
        return source_infos
        
    except Exception as e:
        logger.error(f"資料一覧の取得に失敗: {type(e).__name__}: {e}")
        return []
