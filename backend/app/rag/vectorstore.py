"""
ChromaDB Vector Store（Semantic Retrieval用）
"""
import logging
from pathlib import Path
from typing import List, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

# ロガー設定
logger = logging.getLogger(__name__)

# コレクション名（固定）
COLLECTION_NAME = "rag_chunks"


def get_vectorstore(chroma_dir: str) -> chromadb.Collection:
    """
    ChromaDBコレクションを取得（永続化）
    
    Args:
        chroma_dir: ChromaDBの永続化ディレクトリ
        
    Returns:
        ChromaDBコレクション
        
    Raises:
        KeyError: ChromaDBのDB互換問題が発生した場合（'_type'キーエラー）
    """
    # リポジトリルートを取得
    repo_root = Path(__file__).parent.parent.parent.parent
    chroma_path = repo_root / chroma_dir
    
    # ディレクトリを作成（存在しない場合）
    chroma_path.mkdir(parents=True, exist_ok=True)
    
    # PersistentClientで永続化
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    
    # NEW: コレクションを取得または作成（DB互換問題のエラーハンドリング）
    try:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    except KeyError as e:
        # KeyError '_type' は ChromaDB のバージョン不一致によるDB互換問題
        if "_type" in str(e):
            chroma_db_path = chroma_path / "chroma.sqlite3"
            logger.error(
                f"ChromaDB互換エラーが発生しました（KeyError '_type'）。\n"
                f"原因: ChromaDBのバージョン不一致またはDB形式の互換性問題。\n"
                f"解決方法: 以下のコマンドでDBを削除して再生成してください。\n"
                f"  1. サーバーを停止\n"
                f"  2. 以下のディレクトリを削除: {chroma_path}\n"
                f"  3. サーバーを再起動（起動時に自動的にインデックスが再構築されます）\n"
                f"または手動で削除: rm -rf {chroma_path}\n"
                f"ChromaDBパス: {chroma_db_path}"
            )
        raise
    
    return collection


def upsert_chunks(
    collection: chromadb.Collection,
    ids: List[str],
    embeddings: List[List[float]],
    documents: List[str],
    metadatas: List[dict],
) -> None:
    """
    チャンクをChromaDBに保存（upsert）
    
    Args:
        collection: ChromaDBコレクション
        ids: チャンクIDのリスト（"{source}:{page}:{chunk_index}"）
        embeddings: Embeddingベクトルのリスト
        documents: チャンクテキストのリスト
        metadatas: メタデータのリスト（source, page, chunk_indexを含む）
    """
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query_chunks(
    collection: chromadb.Collection,
    query_embedding: List[float],
    top_k: int,
) -> Tuple[List[str], List[dict], List[float]]:
    """
    チャンクを検索（semantic search）
    
    Args:
        collection: ChromaDBコレクション
        query_embedding: 質問のEmbeddingベクトル
        top_k: 取得件数
        
    Returns:
        (documents, metadatas, distances) のタプル
    """
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    
    # 結果を取得（query_embeddingsが1件なので最初の要素を取得）
    documents = results["documents"][0] if results["documents"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []
    
    return documents, metadatas, distances


def get_collection_count(collection: chromadb.Collection) -> int:
    """
    コレクション内のチャンク数を取得
    
    Args:
        collection: ChromaDBコレクション
        
    Returns:
        チャンク数
    """
    return collection.count()
