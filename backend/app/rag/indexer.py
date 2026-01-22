"""
RAGインデックス作成（ChromaDBへの登録）
"""
import logging
from pathlib import Path
from typing import List

from app.core.settings import settings
from app.docs.loader import load_documents
from app.docs.models import Document
from app.rag.chunking import chunk_document_for_rag
from app.rag.embedding import embed_passages
from app.rag.vectorstore import (
    get_vectorstore,
    upsert_chunks,
    get_collection_count,
)

# ロガー設定
logger = logging.getLogger(__name__)


def build_index(force_rebuild: bool = False) -> None:
    """
    manuals配下のドキュメントをインデックス化（ChromaDBに登録）
    
    - 既存のローダを流用してtxt/pdfを読み込む
    - Document -> chunk_document_for_rag() -> passages embedding -> upsert
    - force_rebuild=True の場合は既存データを無視して再構築
    
    Args:
        force_rebuild: 既存データを無視して強制的に再構築するか
    """
    try:
        # ChromaDBコレクションを取得
        collection = get_vectorstore(settings.chroma_dir)
        
        # 既にデータがある場合はスキップ（force_rebuild=Falseの場合）
        if not force_rebuild:
            existing_count = get_collection_count(collection)
            if existing_count > 0:
                logger.info(f"インデックスは既に存在します（{existing_count}件）。スキップします。")
                return
        
        logger.info("RAGインデックス作成を開始します...")
        
        # ドキュメントを読み込む（既存のローダを流用）
        documents = load_documents(settings.docs_dir)
        
        if len(documents) == 0:
            logger.warning(f"ドキュメントが見つかりません: {settings.docs_dir}")
            return
        
        # 全チャンクを収集（見出し境界優先チャンキング）
        all_chunks = []
        for doc in documents:
            chunks = chunk_document_for_rag(
                doc,
                chunk_size=settings.section_chunk_size,  # セクション単位のチャンクサイズ
                chunk_overlap=settings.section_chunk_overlap,  # セクション単位のオーバーラップ
            )
            all_chunks.extend(chunks)
        
        if len(all_chunks) == 0:
            logger.warning("チャンクが生成されませんでした")
            return
        
        # Embeddingを生成（バッチ処理）
        logger.info(f"Embedding生成中: {len(all_chunks)}件...")
        chunk_texts = [chunk.text for chunk in all_chunks]
        embeddings = embed_passages(chunk_texts, model_name=settings.embedding_model)
        
        # ChromaDBに登録するデータを準備
        ids = []
        documents_list = []
        metadatas = []
        
        for chunk in all_chunks:
            # ID設計: "{source}:{page}:{chunk_index}"
            chunk_id = f"{chunk.source}:{chunk.page}:{chunk.chunk_index}"
            ids.append(chunk_id)
            
            # CHANGED: ドキュメント（チャンクテキスト、全文で保存）
            # APIレスポンス時に400文字で切るが、DBには全文を保持して品質を向上
            documents_list.append(chunk.text)
            
            # メタデータ
            metadatas.append({
                "source": chunk.source,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
            })
        
        # ChromaDBにupsert
        logger.info(f"ChromaDBに登録中: {len(ids)}件...")
        upsert_chunks(
            collection=collection,
            ids=ids,
            embeddings=embeddings,
            documents=documents_list,
            metadatas=metadatas,
        )
        
        # NEW: sourceごとのチャンク数をログ出力（PDFが参照されない原因調査用）
        from collections import Counter
        source_counts = Counter([chunk.source for chunk in all_chunks])
        logger.info(f"Chroma投入チャンクのsource分布: {dict(source_counts)}")
        
        # ログ出力
        doc_count = len(documents)
        chunk_count = len(all_chunks)
        logger.info(f"RAGインデックス作成完了: doc_count={doc_count}, chunk_count={chunk_count}")
        
    except Exception as e:
        # 失敗してもサーバ起動は落とさない（ログだけ出す）
        logger.error(f"RAGインデックス作成に失敗しました: {type(e).__name__}: {e}", exc_info=True)
