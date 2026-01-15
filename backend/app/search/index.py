"""
検索インデックス（暫定実装）
"""
import logging
from typing import List, Optional, Set, Tuple

from app.core.settings import settings
from app.docs.loader import load_documents
from app.docs.chunker import chunk_documents
from app.docs.models import DocumentChunk
from app.search.ngram import score as ngram_score

# ロガー設定
logger = logging.getLogger(__name__)

# グローバルキャッシュ（in-memory）
_cached_chunks: Optional[List[DocumentChunk]] = None


def _build_index() -> List[DocumentChunk]:
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
        _cached_chunks = _build_index()
    
    return _cached_chunks


def search_chunks(query: str, k: int = 5) -> List[tuple[DocumentChunk, int]]:
    """
    チャンクを検索する（暫定実装）
    
    - まず既存の検索方法（スペース区切り・部分文字列）を試す
    - 候補が0件の場合、2-gram検索にフォールバック

    Args:
        query: 検索クエリ
        k: 取得件数

    Returns:
        (DocumentChunk, score)のリスト（score降順）
    """
    chunks = get_chunks()
    
    query = query.strip()
    if not query:
        return []
    
    # 既存の検索方法を試す
    scored_chunks = _search_keyword(query, chunks, k)
    
    # 候補が0件の場合、2-gram検索にフォールバック
    if len(scored_chunks) == 0:
        scored_chunks = _search_ngram(query, chunks, k)
    
    return scored_chunks


def _search_keyword(query: str, chunks: List[DocumentChunk], k: int) -> List[tuple[DocumentChunk, int]]:
    """
    キーワード検索（既存の検索方法）
    
    Args:
        query: 検索クエリ
        chunks: 検索対象チャンク
        k: 取得件数
        
    Returns:
        (DocumentChunk, score)のリスト（score降順）
    """
    # クエリをトークン化（スペース区切り）
    query_tokens = query.split()
    # 全文一致チェック用
    query_lower = query.lower()
    
    # 各chunkをスコアリング
    scored_chunks: List[tuple[DocumentChunk, int]] = []
    
    for chunk in chunks:
        text_lower = chunk.text.lower()
        score = 0
        
        # 全文一致なら+3（高スコア）
        if query_lower in text_lower:
            score += 3
        
        # トークン含有数をカウント（スペース区切りがある場合）
        if len(query_tokens) > 1:
            for token in query_tokens:
                token_lower = token.lower()
                if token_lower in text_lower:
                    score += 1
        
        # 日本語対応：部分文字列マッチング（2文字以上の部分文字列をチェック）
        if len(query) >= 2:
            # クエリの部分文字列（2文字以上）が含まれているかチェック
            for i in range(len(query) - 1):
                substring = query[i:i+2].lower()
                if substring in text_lower:
                    score += 1
                    break  # 1回見つかればOK
        
        # スコアが0より大きい場合のみ追加
        if score > 0:
            scored_chunks.append((chunk, score))
    
    # score降順でソート
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # 上位k件を返す
    return scored_chunks[:k]


def _search_ngram(query: str, chunks: List[DocumentChunk], k: int) -> List[tuple[DocumentChunk, int]]:
    """
    2-gram検索（日本語対応フォールバック）
    
    Args:
        query: 検索クエリ
        chunks: 検索対象チャンク
        k: 取得件数
        
    Returns:
        (DocumentChunk, score)のリスト（score降順、重複排除済み）
    """
    # 各chunkを2-gramスコアで評価
    scored_chunks: List[tuple[DocumentChunk, int]] = []
    
    for chunk in chunks:
        chunk_score = ngram_score(query, chunk.text)
        
        # スコアが0より大きい場合のみ追加
        if chunk_score > 0:
            scored_chunks.append((chunk, chunk_score))
    
    # score降順でソート
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # 重複排除（同一sourceで同じsnippetを除外）
    seen: Set[Tuple[str, str]] = set()
    deduplicated: List[tuple[DocumentChunk, int]] = []
    
    for chunk, score in scored_chunks:
        # スニペットの簡易版（先頭50文字）で重複判定
        snippet_key = chunk.text[:50].strip()
        key = (chunk.source, snippet_key)
        
        if key not in seen:
            seen.add(key)
            deduplicated.append((chunk, score))
            
            # k件に達したら終了
            if len(deduplicated) >= k:
                break
    
    return deduplicated


def create_snippet(text: str, query: str, max_length: int = 120) -> str:
    """
    スニペット（抜粋）を作成する

    Args:
        text: 元のテキスト
        query: 検索クエリ
        max_length: 最大文字数

    Returns:
        スニペット文字列
    """
    text_lower = text.lower()
    query_lower = query.lower()
    
    # クエリが含まれる位置を探す（最初の出現位置）
    query_pos = text_lower.find(query_lower)
    
    if query_pos == -1:
        # クエリが見つからない場合は先頭から
        snippet = text[:max_length].strip()
        if len(text) > max_length:
            snippet = snippet[:max_length - 3] + "..."
    else:
        # クエリの前後を取得（前後40文字ずつ）
        context_length = 40
        start = max(0, query_pos - context_length)
        end = min(len(text), query_pos + len(query) + context_length)
        snippet = text[start:end].strip()
        
        # 先頭が途中なら「...」を付ける
        if start > 0:
            snippet = "..." + snippet
        # 末尾が途中なら「...」を付ける
        if end < len(text):
            snippet = snippet + "..."
    
    # 改行を削除して1行に
    snippet = snippet.replace("\n", " ").replace("\r", " ")
    # 連続する空白を1つに
    while "  " in snippet:
        snippet = snippet.replace("  ", " ")
    
    # 重複した文を削除（同じ文が2回以上続く場合、最初の1回だけ残す）
    # 簡易的な重複除去：同じパターンが繰り返される場合を検出
    words = snippet.split()
    if len(words) > 10:
        # 最初の10単語と次の10単語が同じなら、最初だけ残す
        first_10 = " ".join(words[:10])
        if len(words) >= 20:
            second_10 = " ".join(words[10:20])
            if first_10 == second_10:
                # 重複を検出した場合、最初の部分だけを返す
                snippet = first_10 + "..."
    
    # 最大長を超える場合は切り詰め
    if len(snippet) > max_length:
        snippet = snippet[:max_length - 3] + "..."
    
    return snippet


def create_quote(chunk: DocumentChunk, query: str = "", max_length: int = 240) -> str:
    """
    引用用のquoteを作成する（citations用）

    Args:
        chunk: DocumentChunk
        query: 検索クエリ（クエリ位置を優先する場合に使用）
        max_length: 最大文字数

    Returns:
        quote文字列
    """
    text = chunk.text.strip()
    
    # 改行を空白に置換
    text = text.replace("\n", " ").replace("\r", " ")
    # 連続する空白を1つに
    while "  " in text:
        text = text.replace("  ", " ")
    
    # クエリが指定されている場合は、クエリ位置を優先して抜粋
    if query and len(query) > 0:
        text_lower = text.lower()
        query_lower = query.lower()
        
        # クエリが含まれる位置を探す（最初の出現位置）
        query_pos = text_lower.find(query_lower)
        
        if query_pos != -1:
            # クエリの前後を取得（前後50%ずつ）
            context_length = max_length // 2
            start = max(0, query_pos - context_length)
            end = min(len(text), query_pos + len(query) + context_length)
            quote = text[start:end].strip()
            
            # 先頭が途中なら「…」を付ける
            if start > 0:
                quote = "…" + quote
            # 末尾が途中なら「…」を付ける
            if end < len(text):
                quote = quote + "…"
            
            # 最大長を超える場合は切り詰め
            if len(quote) > max_length:
                quote = quote[:max_length - 1] + "…"
            
            return quote
    
    # クエリが見つからない、または指定されていない場合は先頭から
    if len(text) > max_length:
        text = text[:max_length - 1] + "…"
    
    return text
