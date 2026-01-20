"""
キーワード検索（改善版：ストップワード除去、最小スコア閾値）
"""
import logging
from typing import List

from app.core.settings import settings
from app.docs.models import DocumentChunk
from app.search.stopwords import remove_stopwords
from app.search.ngram import score as ngram_score

# ロガー設定
logger = logging.getLogger(__name__)


def search_keyword(query: str, chunks: List[DocumentChunk], k: int) -> List[tuple[DocumentChunk, int]]:
    """
    キーワード検索（改善版：ストップワード除去、最小スコア閾値）
    
    Args:
        query: 検索クエリ
        chunks: 検索対象チャンク
        k: 取得件数
        
    Returns:
        (DocumentChunk, score)のリスト（score降順）
    """
    # クエリをトークン化してストップワードを除去
    query_tokens_raw = query.split()
    query_tokens = remove_stopwords(query_tokens_raw)
    
    # ログ出力（観測性強化）
    logger.info(
        f"keyword検索開始: query='{query}', "
        f"tokens_raw={query_tokens_raw}, "
        f"tokens_filtered={query_tokens}"
    )
    
    # 全文一致チェック用
    query_lower = query.lower()
    
    # 最小スコア閾値（settingsから取得、調整可能）
    min_score_threshold = settings.keyword_min_score
    
    # 各chunkをスコアリング
    scored_chunks: List[tuple[DocumentChunk, int]] = []
    
    for chunk in chunks:
        score = _calculate_chunk_score(chunk.text, query_lower, query, query_tokens)
        
        # 最小スコア閾値を適用（ノイズ除去）
        if score >= min_score_threshold:
            scored_chunks.append((chunk, score))
    
    # score降順でソート
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # ログ出力（観測性強化）
    logger.info(
        f"keyword検索結果: total_hits={len(scored_chunks)}, "
        f"top3_scores={[score for _, score in scored_chunks[:3]]}, "
        f"min_threshold={min_score_threshold}"
    )
    
    # 上位k件を返す
    return scored_chunks[:k]


def _calculate_chunk_score(
    text: str,
    query_lower: str,
    query_original: str,
    query_tokens: List[str]
) -> int:
    """
    チャンクのスコアを計算
    
    Args:
        text: チャンクテキスト
        query_lower: 小文字化されたクエリ
        query_original: 元のクエリ
        query_tokens: ストップワード除去後のトークン
        
    Returns:
        スコア
    """
    text_lower = text.lower()
    score = 0
    
    # 全文一致なら+5（高スコア）
    if query_lower in text_lower:
        score += 5
    
    # ストップワード除去後のトークンで評価
    if len(query_tokens) > 0:
        matched_tokens = 0
        for token in query_tokens:
            token_lower = token.lower()
            if len(token_lower) >= 2 and token_lower in text_lower:
                matched_tokens += 1
                score += 2  # トークンマッチは+2
        
        # マッチ率ボーナス（全トークンの50%以上マッチした場合）
        if len(query_tokens) > 0 and matched_tokens >= len(query_tokens) * 0.5:
            score += 3
    
    # 3文字以上の連続文字列でマッチングを試みる
    if len(query_original) >= 3:
        query_clean = query_original.replace(" ", "").replace("？", "").replace("?", "")
        if len(query_clean) >= 3:
            # 3文字単位でチェック（重要な単語のみ）
            for i in range(len(query_clean) - 2):
                substring = query_clean[i:i+3].lower()
                if substring in text_lower:
                    score += 1
                    break  # 1回見つかればOK
    
    return score


def search_ngram(query: str, chunks: List[DocumentChunk], k: int) -> List[tuple[DocumentChunk, int]]:
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
    seen = set()
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
