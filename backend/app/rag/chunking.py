"""
日本語前提のチャンキング
"""
import re
from typing import List

from app.docs.models import Document, DocumentChunk


def chunk_text_japanese(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    日本語テキストをチャンクに分割（改行・句点ベース、それでも長い場合は固定長）
    
    Args:
        text: 元のテキスト
        chunk_size: チャンクサイズ（文字数）
        chunk_overlap: オーバーラップ文字数
        
    Returns:
        チャンクテキストのリスト
    """
    chunks = []
    
    # 改行で分割（段落単位）
    paragraphs = text.split('\n')
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # 現在のチャンクに追加した場合の長さを確認
        if current_chunk:
            test_chunk = current_chunk + "\n" + para
        else:
            test_chunk = para
        
        if len(test_chunk) <= chunk_size:
            # チャンクサイズ内なら追加
            if current_chunk:
                current_chunk += "\n" + para
            else:
                current_chunk = para
        else:
            # チャンクサイズを超える場合
            if current_chunk:
                # 現在のチャンクを保存
                chunks.append(current_chunk)
                
                # オーバーラップ分を次のチャンクの先頭に
                if chunk_overlap > 0 and len(current_chunk) >= chunk_overlap:
                    overlap_text = current_chunk[-chunk_overlap:]
                    current_chunk = overlap_text + "\n" + para
                else:
                    current_chunk = para
            else:
                # 現在のチャンクが空で、段落が長すぎる場合は句点で分割
                if len(para) > chunk_size:
                    # 句点（。、！？）で分割
                    sentences = re.split(r'([。！？\n])', para)
                    sentence_chunk = ""
                    
                    for i in range(0, len(sentences), 2):
                        if i + 1 < len(sentences):
                            sentence = sentences[i] + sentences[i + 1]
                        else:
                            sentence = sentences[i]
                        
                        if len(sentence_chunk) + len(sentence) <= chunk_size:
                            sentence_chunk += sentence
                        else:
                            if sentence_chunk:
                                chunks.append(sentence_chunk)
                                # オーバーラップ
                                if chunk_overlap > 0 and len(sentence_chunk) >= chunk_overlap:
                                    current_chunk = sentence_chunk[-chunk_overlap:] + sentence
                                else:
                                    current_chunk = sentence
                                sentence_chunk = ""
                            else:
                                # 1文が長すぎる場合は固定長で分割
                                for j in range(0, len(sentence), chunk_size - chunk_overlap):
                                    chunk_text = sentence[j:j + chunk_size]
                                    if chunk_text.strip():
                                        chunks.append(chunk_text)
                    if sentence_chunk:
                        current_chunk = sentence_chunk
                else:
                    current_chunk = para
    
    # 最後のチャンクを追加
    if current_chunk:
        chunks.append(current_chunk)
    
    # CHANGED: 関数末尾で必ず return chunks（ifブロック内に入れない）
    return chunks


def chunk_document_for_rag(document: Document, chunk_size: int, chunk_overlap: int) -> List[DocumentChunk]:
    """
    ドキュメントをRAG用にチャンクに分割
    
    Args:
        document: ドキュメント
        chunk_size: チャンクサイズ
        chunk_overlap: オーバーラップ文字数
        
    Returns:
        DocumentChunkのリスト
    """
    chunk_texts = chunk_text_japanese(document.text, chunk_size, chunk_overlap)
    
    chunks = []
    for i, chunk_text in enumerate(chunk_texts):
        chunks.append(
            DocumentChunk(
                source=document.source,
                page=document.page,
                chunk_index=i,
                text=chunk_text,
            )
        )
    
    # CHANGED: return chunks を for ループ外へ出す（1周目でreturnしない）
    return chunks
