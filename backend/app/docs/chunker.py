"""
ドキュメントチャンク分割モジュール
"""
from typing import List

from app.docs.models import Document, DocumentChunk


def chunk_document(document: Document) -> List[DocumentChunk]:
    """
    ドキュメントをチャンクに分割する（LEN戦略）

    Args:
        document: ドキュメント

    Returns:
        DocumentChunkのリスト
    """
    text = document.text
    text_len = len(text)

    # 文字数に応じてchunk_sizeとoverlapを決定
    if text_len <= 4000:
        chunk_size = 800
        overlap = 120
    elif text_len <= 20000:
        chunk_size = 1200
        overlap = 180
    else:
        chunk_size = 1600
        overlap = 240

    chunks = []
    start = 0
    chunk_index = 0

    while start < text_len:
        end = start + chunk_size
        chunk_text = text[start:end]

        # チャンクが空でない場合のみ追加
        if chunk_text.strip():
            chunks.append(
                DocumentChunk(
                    source=document.source,
                    page=document.page,
                    chunk_index=chunk_index,
                    text=chunk_text,
                )
            )
            chunk_index += 1

        # 次のチャンクの開始位置（overlap分戻る）
        start = end - overlap
        if start >= text_len:
            break

    return chunks


def chunk_documents(documents: List[Document]) -> List[DocumentChunk]:
    """
    複数のドキュメントをチャンクに分割する

    Args:
        documents: ドキュメントのリスト

    Returns:
        DocumentChunkのリスト
    """
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)
    return all_chunks
