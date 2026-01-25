"""
検索インデックス（キーワード・2-gram検索用）

【初心者向け】
- RAGの「キーワード検索」で利用。Semantic(Chroma)とは別に、単語マッチで候補を出す
- チャンクは docs の loader/chunker で作り、メモリにキャッシュ
- 検索: キーワード＋最小スコア閾値 → ヒット0件なら2-gramでフォールバック
"""
import logging
from typing import List, Optional, Set, Tuple

from app.core.settings import settings
from app.docs.loader import load_documents
from app.docs.chunker import chunk_documents
from app.docs.models import DocumentChunk
from app.search.ngram import score as ngram_score
from app.search.stopwords import remove_stopwords  # NEW

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


def search_chunks(query: str, k: int = 5, source_filter: Optional[List[str]] = None) -> List[tuple[DocumentChunk, int]]:
    """
    チャンクを検索する（暫定実装）
    
    - まず既存の検索方法（スペース区切り・部分文字列）を試す
    - 候補が0件の場合、2-gram検索にフォールバック

    Args:
        query: 検索クエリ
        k: 取得件数
        source_filter: ソースフィルタ（None=フィルタなし）

    Returns:
        (DocumentChunk, score)のリスト（score降順）
    """
    chunks = get_chunks()
    
    query = query.strip()
    if not query:
        return []
    
    # source_filterがある場合は事前にフィルタリング
    if source_filter is not None:
        chunks = [chunk for chunk in chunks if chunk.source in source_filter]
    
    # 既存の検索方法を試す
    scored_chunks = _search_keyword(query, chunks, k)
    
    # 候補が0件の場合、2-gram検索にフォールバック
    if len(scored_chunks) == 0:
        scored_chunks = _search_ngram(query, chunks, k)
    
    return scored_chunks


def _search_keyword(query: str, chunks: List[DocumentChunk], k: int) -> List[tuple[DocumentChunk, int]]:
    """
    キーワード検索（改善版：ストップワード除去、最小スコア閾値）
    
    Args:
        query: 検索クエリ
        chunks: 検索対象チャンク
        k: 取得件数
        
    Returns:
        (DocumentChunk, score)のリスト（score降順）
    """
    # CHANGED: クエリをトークン化してストップワードを除去
    query_tokens_raw = query.split()
    query_tokens = remove_stopwords(query_tokens_raw)  # NEW: ストップワード除去
    
    # NEW: ログ出力（観測性強化）
    logger.info(
        f"keyword検索開始: query='{query}', "
        f"tokens_raw={query_tokens_raw}, "
        f"tokens_filtered={query_tokens}"
    )
    
    # 全文一致チェック用
    query_lower = query.lower()
    
    # NEW: 最小スコア閾値（settingsから取得、調整可能）
    MIN_SCORE_THRESHOLD = settings.keyword_min_score
    
    # 各chunkをスコアリング
    scored_chunks: List[tuple[DocumentChunk, int]] = []
    
    for chunk in chunks:
        text_lower = chunk.text.lower()
        score = 0
        
        # 全文一致なら+5（高スコア、CHANGED: 3→5に引き上げ）
        if query_lower in text_lower:
            score += 5
        
        # NEW: 重要なキーワード（質問の核心部分）を抽出して評価
        # 質問から重要な名詞を抽出（簡易版：2文字以上の連続文字列）
        # ストップワードを除去して核心部分を抽出
        stopwords = ["です", "か", "たら", "どう", "したら", "いい", "ですか", "？", "?", "が", "を", "に", "は", "の", "と", "で", "から", "まで", "より", "も", "や", "など"]
        query_clean = query
        for sw in stopwords:
            query_clean = query_clean.replace(sw, " ")
        query_clean = " ".join(query_clean.split())  # 連続空白を1つに
        
        # NEW: まず、既知の重要な単語（3文字以上）を直接検出
        # これにより「強盗」「万引き」などの単語が確実に検出される
        important_keywords = []
        query_chars = query_clean.replace(" ", "")
        
        # 3文字以上の連続文字列を優先的に抽出（単語として認識しやすい）
        if len(query_chars) >= 3:
            for i in range(len(query_chars) - 2):
                keyword = query_chars[i:i+3]
                if keyword not in important_keywords:
                    important_keywords.append(keyword)
        
        # 2文字の連続文字列も追加（補完用）
        if len(query_chars) >= 2:
            for i in range(len(query_chars) - 1):
                keyword = query_chars[i:i+2]
                if keyword not in important_keywords:
                    important_keywords.append(keyword)
        
        # 重要なキーワードが含まれている場合は高スコア
        # 特に「強盗」などの具体的な名詞が含まれている場合は最高スコア
        for keyword in important_keywords:
            if keyword in text_lower:
                # 3文字以上のキーワードはより重要
                if len(keyword) >= 3:
                    score += 20  # CHANGED: 15→20に引き上げ（重要キーワード（3文字以上）マッチは最高スコア）
                else:
                    score += 10  # CHANGED: 8→10に引き上げ（重要キーワード（2文字）マッチは高スコア）
        
        # CHANGED: ストップワード除去後のトークンで評価
        if len(query_tokens) > 0:
            matched_tokens = 0
            for token in query_tokens:
                token_lower = token.lower()
                if len(token_lower) >= 2 and token_lower in text_lower:  # NEW: 2文字以上のみ
                    matched_tokens += 1
                    score += 2  # CHANGED: トークンマッチは+2に強化
            
            # NEW: マッチ率ボーナス（全トークンの50%以上マッチした場合）
            if len(query_tokens) > 0 and matched_tokens >= len(query_tokens) * 0.5:
                score += 3
        
        # CHANGED: 部分文字列マッチングは削除（ノイズが多いため）
        # 代わりに、3文字以上のキーワードを抽出して評価
        # クエリから3文字以上の連続文字列を抽出（日本語対応）
        if len(query) >= 3:
            # 3文字以上の部分文字列でマッチングを試みる
            query_clean = query.replace(" ", "").replace("？", "").replace("?", "")
            if len(query_clean) >= 3:
                # 3文字単位でチェック（重要な単語のみ）
                for i in range(len(query_clean) - 2):
                    substring = query_clean[i:i+3].lower()
                    if substring in text_lower:
                        score += 1
                        break  # 1回見つかればOK
        
        # CHANGED: 最小スコア閾値を適用（ノイズ除去）
        if score >= MIN_SCORE_THRESHOLD:
            scored_chunks.append((chunk, score))
    
    # score降順でソート
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # NEW: ログ出力（観測性強化）
    logger.info(
        f"keyword検索結果: total_hits={len(scored_chunks)}, "
        f"top3_scores={[score for _, score in scored_chunks[:3]]}, "
        f"min_threshold={MIN_SCORE_THRESHOLD}"
    )
    
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
