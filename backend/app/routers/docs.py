"""
Docs APIルーター
"""
from fastapi import APIRouter

from app.core.settings import settings
from app.docs.loader import load_documents
from app.docs.chunker import chunk_documents

router = APIRouter()


@router.get("/summary")
async def get_docs_summary():
    """
    ドキュメントのサマリーを取得する

    Returns:
        docs数、総文字数、チャンク数
    """
    # ドキュメントを読み込む
    documents = load_documents(settings.docs_dir)

    # 総文字数を計算
    total_chars = sum(len(doc.text) for doc in documents)

    # チャンクに分割
    chunks = chunk_documents(documents)

    return {
        "doc_count": len(documents),
        "total_chars": total_chars,
        "chunk_count": len(chunks),
    }
