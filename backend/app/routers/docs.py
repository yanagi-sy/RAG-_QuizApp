"""
Docs APIルーター
"""
from fastapi import APIRouter

from app.core.settings import settings
from app.docs.loader import load_documents, load_documents_by_file
from app.docs.chunker import chunk_documents, chunk_file_documents

router = APIRouter()


@router.get("/summary")
async def get_docs_summary():
    """
    ドキュメントのサマリーを取得する

    Returns:
        docs数、総文字数、チャンク数、ファイル単位の詳細情報
    """
    # ファイル単位でドキュメントを読み込む
    files_dict = load_documents_by_file(settings.docs_dir)
    
    # ファイル単位の情報を集計
    files_info = []
    total_chars = 0
    total_chunks = 0
    
    for source, file_documents in files_dict.items():
        # ファイル全体の文字数を計算
        file_chars = sum(len(doc.text) for doc in file_documents)
        total_chars += file_chars
        
        # カテゴリ判定とチャンク化
        category, chunk_size, chunk_overlap, chunks = chunk_file_documents(file_documents)
        total_chunks += len(chunks)
        
        files_info.append({
            "source": source,
            "chars": file_chars,
            "category": category,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunks": len(chunks),
        })
    
    # 後方互換のため、従来のdoc_countも計算（ページ単位）
    documents = load_documents(settings.docs_dir)
    
    return {
        "doc_count": len(documents),
        "total_chars": total_chars,
        "chunk_count": total_chunks,
        "files": files_info,
    }
