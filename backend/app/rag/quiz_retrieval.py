"""
Quiz専用の候補取得ロジック

/ask とは独立した、クイズ生成に特化した検索処理。
- semantic検索のみ（抽象的なクエリに強い）
- rerankは順位付けのみ（閾値で全落ちさせない）
- 最低N件を必ず返す（LLM生成の材料確保）
"""
import logging
import time
import unicodedata
from typing import List, Dict, Optional

from app.core.settings import settings
from app.rag.embedding import embed_query
from app.rag.vectorstore import get_vectorstore, query_chunks
from app.search.reranker import rerank_documents
from app.schemas.common import Citation

logger = logging.getLogger(__name__)


def quiz_retrieve_chunks(
    query: str,
    *,
    source_filter: Optional[List[str]] = None,
    k: Optional[int] = None,
    semantic_weight: Optional[float] = None,
) -> tuple[List[Citation], Optional[Dict]]:
    """
    クイズ生成用の候補チャンクを取得
    
    処理フロー:
    1. semantic検索でk件取得（source_filter適用）
    2. rerankで順位を調整（閾値なし、最低N件は必ず返す）
    3. 上位 QUIZ_CONTEXT_TOP_N 件をCitationとして返す
    
    Args:
        query: 検索クエリ
        source_filter: 検索対象のsourceリスト（Noneなら全資料対象）
        k: 候補取得件数（デフォルト: settings.quiz_candidate_k）
        semantic_weight: semantic検索の重み（デフォルト: settings.quiz_semantic_weight）
        
    Returns:
        (Citationのリスト, debug情報の辞書またはNone)のタプル
    """
    # デフォルト値の設定
    if k is None:
        k = settings.quiz_candidate_k
    if semantic_weight is None:
        semantic_weight = settings.quiz_semantic_weight
    
    # source_filter を Unicode NFC 正規化
    if source_filter:
        source_filter = [unicodedata.normalize("NFC", s) for s in source_filter]
        logger.info(f"[Quiz] source_filter を NFC 正規化: {source_filter}")
    
    # semantic検索でk件取得
    collection = get_vectorstore(settings.chroma_dir)
    
    # クエリの埋め込み
    query_embedding = embed_query(query, model_name=settings.embedding_model)
    
    # where条件を構築
    where_filter = None
    if source_filter:
        where_filter = {"source": {"$in": source_filter}}
    
    # semantic検索を実行
    documents, metadatas, distances = query_chunks(
        collection=collection,
        query_embedding=query_embedding,
        top_k=k,
        where_filter=where_filter,
    )
    
    semantic_count = len(documents)
    logger.info(f"[Quiz] semantic検索: {semantic_count}件取得, distances_top3={distances[:3]}")
    
    # 候補が0件の場合は空リストを返す
    if semantic_count == 0:
        logger.warning("[Quiz] semantic検索の結果が0件でした")
        return ([], None)
    
    # rerankで順位を調整（閾値なし、順位付けのみ）
    citations = []
    debug_info: Optional[Dict] = None
    t_rerank_ms = 0.0
    
    if settings.quiz_rerank_enabled and semantic_count > 0:
        # 高速化: rerank対象数を制限（quiz_rerank_max_n件まで）
        rerank_n = min(semantic_count, settings.quiz_rerank_max_n)
        
        # Cross-Encoder用のドキュメントリスト作成
        documents_for_rerank = [
            (text, {"source": meta.get("source", ""), "page": meta.get("page", 0), "chunk_index": meta.get("chunk_index", 0)})
            for text, meta in zip(documents[:rerank_n], metadatas[:rerank_n])
        ]
        
        try:
            # rerankを実行（上位rerank_n件のみ、閾値なし）
            t_rerank_start = time.perf_counter()
            reranked = rerank_documents(
                query=query,
                documents=documents_for_rerank,
                model_name=settings.rerank_model,
                top_n=None,  # 全件再スコアリング
                batch_size=settings.rerank_batch_size,
            )
            t_rerank_ms = (time.perf_counter() - t_rerank_start) * 1000
            
            rerank_count = len(reranked)
            logger.info(f"[Quiz] rerank完了: {rerank_count}件")
            
            # 上位 QUIZ_CONTEXT_TOP_N 件をCitationとして作成（閾値なし、必ず返す）
            top_n = min(settings.quiz_context_top_n, rerank_count)
            
            # 重複排除用のセット
            seen_quotes = set()
            
            for text, metadata, rerank_score in reranked[:top_n * 2]:  # 重複を考慮して多めに取得
                source = metadata["source"]
                page = metadata["page"]
                
                # 重複排除（source, page, quote先頭60文字）
                quote_prefix = text[:60].strip()
                quote_key = (source, page, quote_prefix)
                
                if quote_key not in seen_quotes:
                    seen_quotes.add(quote_key)
                    
                    # pageの扱い：txtはnull、pdfは1以上をそのまま返す
                    page_value = page if page is not None and page > 0 else None
                    
                    # 高速化: quoteを quiz_quote_max_len で切る（デフォルト200文字）
                    max_len = settings.quiz_quote_max_len
                    quote = text[:max_len] if len(text) > max_len else text
                    
                    citations.append(
                        Citation(
                            source=source,
                            page=page_value,
                            quote=quote,
                        )
                    )
                    
                    if len(citations) >= top_n:
                        break
            
            logger.info(f"[Quiz] citations作成完了: {len(citations)}件")
            
            # debug情報を構築
            debug_info = {
                "quiz_candidate_count": semantic_count,
                "quiz_rerank_count": rerank_count,
                "quiz_rerank_time_ms": round(t_rerank_ms, 1),
                "quiz_context_top_n": top_n,
                "quiz_final_citations_count": len(citations),
                "quiz_sources_unique": sorted(set(c.source for c in citations)),
                "quiz_rerank_topN": [
                    {
                        "source": metadata["source"],
                        "page": metadata["page"],
                        "rerank_score": round(rerank_score, 4),
                    }
                    for text, metadata, rerank_score in reranked[:5]  # 上位5件のみ
                ],
            }
            
            if source_filter:
                debug_info["quiz_allowed_sources"] = source_filter
            
        except Exception as e:
            logger.error(f"[Quiz] rerank失敗: {type(e).__name__}: {e}")
            # フォールバック: semantic検索の順位をそのまま使用
            citations = _create_citations_from_semantic(documents, metadatas, settings.quiz_context_top_n)
            debug_info = {
                "quiz_candidate_count": semantic_count,
                "quiz_rerank_enabled": False,
                "quiz_rerank_error": str(e),
                "quiz_final_citations_count": len(citations),
                "quiz_sources_unique": sorted(set(c.source for c in citations)),
            }
    else:
        # rerankなし: semantic検索の順位をそのまま使用
        logger.info("[Quiz] rerank無効: semantic順位を使用")
        citations = _create_citations_from_semantic(documents, metadatas, settings.quiz_context_top_n)
        debug_info = {
            "quiz_candidate_count": semantic_count,
            "quiz_rerank_enabled": False,
            "quiz_final_citations_count": len(citations),
            "quiz_sources_unique": sorted(set(c.source for c in citations)),
        }
    
    return (citations, debug_info)


def _create_citations_from_semantic(
    documents: List[str],
    metadatas: List[Dict],
    top_n: int,
) -> List[Citation]:
    """
    semantic検索結果からcitationsを作成（rerankなしのフォールバック）
    
    Args:
        documents: ドキュメントテキストのリスト
        metadatas: メタデータのリスト
        top_n: 取得件数
        
    Returns:
        Citationのリスト
    """
    citations = []
    seen_quotes = set()
    
    for text, meta in zip(documents[:top_n * 2], metadatas[:top_n * 2]):  # 重複を考慮して多めに取得
        source = meta.get("source", "")
        page = meta.get("page", 0)
        
        # 重複排除
        quote_prefix = text[:60].strip()
        quote_key = (source, page, quote_prefix)
        
        if quote_key not in seen_quotes:
            seen_quotes.add(quote_key)
            
            page_value = page if page is not None and page > 0 else None
            # 高速化: quoteを quiz_quote_max_len で切る（デフォルト200文字）
            max_len = settings.quiz_quote_max_len
            quote = text[:max_len] if len(text) > max_len else text
            
            citations.append(
                Citation(
                    source=source,
                    page=page_value,
                    quote=quote,
                )
            )
            
            if len(citations) >= top_n:
                break
    
    return citations
