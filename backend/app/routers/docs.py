"""
Docs APIルーター（ドキュメント概要・ソース一覧のエンドポイント）

【初心者向け】
- GET /docs/summary: ファイル単位の文字数・チャンク数・カテゴリなど
- GET /docs/sources: ChromaDBから登録済みソース名の一覧を返す
"""
from fastapi import APIRouter
from typing import List

from app.core.settings import settings
from app.docs.loader import load_documents, load_documents_by_file
from app.docs.chunker import chunk_documents, chunk_file_documents
from app.rag.vectorstore import get_vectorstore

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


@router.get("/sources")
async def get_available_sources() -> List[str]:
    """
    利用可能なソースファイルのリストを取得する（ChromaDBから）
    
    Returns:
        ソースファイル名のリスト（ソート済み）
    """
    try:
        collection = get_vectorstore(settings.chroma_dir)
        
        # ChromaDBから全チャンクを取得（メタデータのみ）
        # 大量データの場合は効率化が必要だが、現状は全件取得
        results = collection.get(limit=10000)  # 十分大きな値
        
        # ユニークなsourceを抽出
        sources = set()
        if results.get("metadatas"):
            for metadata in results["metadatas"]:
                source = metadata.get("source")
                if source:
                    sources.add(source)
        
        # ソートして返す
        return sorted(list(sources))
        
    except Exception as e:
        # エラー時は空リストを返す（フロントエンドでエラーハンドリング可能）
        return []
