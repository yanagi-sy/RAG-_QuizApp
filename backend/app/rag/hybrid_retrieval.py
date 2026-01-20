"""
Hybrid Retrieval（RRF融合 + Cross-Encoderリランキング）

/ask API専用の検索ロジック。
semantic検索とkeyword検索を組み合わせ、高品質な引用を取得する。
"""
import logging
import unicodedata
from typing import Dict, Tuple, List, Optional

from app.core.settings import settings
from app.schemas.common import Citation
from app.rag.embedding import embed_query
from app.rag.vectorstore import get_collection_count, get_vectorstore, query_chunks
from app.search.index import search_chunks
from app.search.reranker import rerank_documents

logger = logging.getLogger(__name__)


def hybrid_retrieval(
    query: str,
    semantic_weight: float,
    keyword_weight: float,
    top_k: int,
    include_debug: bool = False,
    source_filter: Optional[List[str]] = None,
) -> Tuple[List[Citation], Optional[Dict], Optional[List[Dict]]]:
    """
    Hybrid retrieval（RRF融合 + Cross-Encoderリランキング）でcitationsを作成
    
    パイプライン:
    1. semantic/keyword検索でそれぞれcandidate_k件取得
    2. RRF（順位融合）でマージ・ソート
    3. 上位rerank_n件をCross-Encoderで再スコアリング
    4. 最終top_k件をcitationsとして返す
    
    Args:
        query: 検索クエリ
        semantic_weight: semantic検索の重み（RRFの重み付けに使用）
        keyword_weight: keyword検索の重み（RRFの重み付けに使用）
        top_k: 最終的に返す件数
        include_debug: debug情報を含めるかどうか
        source_filter: 検索対象のsourceリスト（Noneなら全資料対象）
        
    Returns:
        (Citationのリスト, debug情報の辞書またはNone, quiz_candidates)のタプル
        - quiz_candidates: post_rerank 上位N件（quiz救済用、常に作成）
    """
    debug_info: Optional[Dict] = None
    quiz_candidates: Optional[List[Dict]] = None
    
    # source_filter をUnicode NFC正規化
    if source_filter:
        source_filter = [unicodedata.normalize("NFC", s) for s in source_filter]
        logger.info(f"source_filter を NFC 正規化しました: {source_filter}")
    
    # 候補数を総チャンク数から動的に決定
    collection = get_vectorstore(settings.chroma_dir)
    collection_count = get_collection_count(collection)
    
    if collection_count == 0:
        logger.warning("Chroma collection is empty. Run build_index first.")
        return ([], debug_info, quiz_candidates)
    
    candidate_k = max(
        settings.candidate_min_k,
        min(
            settings.candidate_max_k,
            round(collection_count * settings.candidate_ratio)
        )
    )
    
    rerank_n = max(
        settings.rerank_min_n,
        min(
            settings.rerank_max_n,
            round(candidate_k * settings.rerank_ratio)
        )
    )
    
    logger.info(
        f"候補数決定: collection_count={collection_count}, "
        f"candidate_k={candidate_k}, rerank_n={rerank_n}, top_k={top_k}"
    )
    
    # semantic検索を実行
    semantic_results, semantic_before_filter, semantic_after_filter, semantic_sources_before = \
        _perform_semantic_search(query, candidate_k, source_filter, collection)
    
    # keyword検索を実行
    keyword_results, keyword_before_filter, keyword_after_filter, keyword_sources_before = \
        _perform_keyword_search(query, candidate_k, source_filter)
    
    # RRF融合でマージ
    rrf_results = _merge_with_rrf(
        semantic_results,
        keyword_results,
        semantic_weight,
        keyword_weight,
        candidate_k
    )
    
    sorted_rrf = sorted(
        rrf_results.items(),
        key=lambda x: x[1][1],  # rrf_scoreでソート
        reverse=True
    )
    
    logger.info(
        f"RRF融合: merged={len(rrf_results)}件, "
        f"top3_rrf_scores={[score for _, (_, score, _, _) in sorted_rrf[:3]]}"
    )
    
    # Cross-Encoderでリランキング
    citations, quiz_candidates, post_rerank_count, after_threshold_count, \
        pre_rerank_info, post_rerank_info, post_rerank_with_text = \
        _perform_reranking(query, sorted_rrf, rerank_n, top_k, include_debug, source_filter)
    
    # debug情報を構築
    if include_debug:
        debug_info = _build_debug_info(
            collection_count, candidate_k, rerank_n, top_k,
            semantic_before_filter, semantic_after_filter,
            keyword_before_filter, keyword_after_filter,
            len(rrf_results), post_rerank_count, after_threshold_count,
            len(citations), len(semantic_results), len(keyword_results),
            pre_rerank_info, post_rerank_info, post_rerank_with_text,
            citations, source_filter,
            semantic_sources_before, keyword_sources_before
        )
    
    return (citations, debug_info, quiz_candidates)


def _perform_semantic_search(
    query: str,
    candidate_k: int,
    source_filter: Optional[List[str]],
    collection
) -> Tuple[Dict, int, int, List[str]]:
    """
    semantic検索を実行してフィルタリング
    
    Returns:
        (semantic_results, before_filter_count, after_filter_count, sources_before)
    """
    semantic_results: Dict[Tuple[str, int, int], Tuple[str, int]] = {}
    semantic_before_filter = 0
    semantic_after_filter = 0
    semantic_sources_before = []
    
    try:
        query_embedding = embed_query(query, model_name=settings.embedding_model)
        
        # フィルタなしで取得
        documents_all, metadatas_all, distances_all = query_chunks(
            collection=collection,
            query_embedding=query_embedding,
            top_k=candidate_k,
            where_filter=None,
        )
        semantic_before_filter = len(documents_all)
        semantic_sources_before = [m.get("source", "") for m in metadatas_all]
        
        # source_filter適用
        if source_filter:
            filtered_docs = []
            filtered_metas = []
            for doc_text, metadata in zip(documents_all, metadatas_all):
                source = metadata.get("source", "")
                source_normalized = unicodedata.normalize("NFC", source)
                if source_normalized in source_filter:
                    filtered_docs.append(doc_text)
                    filtered_metas.append(metadata)
            
            documents = filtered_docs
            metadatas = filtered_metas
        else:
            documents = documents_all
            metadatas = metadatas_all
        
        semantic_after_filter = len(documents)
        
        # semantic_resultsに格納
        for rank, (doc_text, metadata) in enumerate(zip(documents, metadatas)):
            source = metadata.get("source", "")
            page = metadata.get("page", 0)
            chunk_index = metadata.get("chunk_index", 0)
            key = (source, page, chunk_index)
            semantic_results[key] = (doc_text, rank + 1)
        
        logger.info(
            f"semantic検索: before_filter={semantic_before_filter}, "
            f"after_filter={semantic_after_filter}, distances_top3={distances_all[:3]}"
        )
    except Exception as e:
        logger.warning(f"Semantic検索に失敗: {type(e).__name__}: {e}")
    
    return (semantic_results, semantic_before_filter, semantic_after_filter, semantic_sources_before)


def _perform_keyword_search(
    query: str,
    candidate_k: int,
    source_filter: Optional[List[str]]
) -> Tuple[Dict, int, int, List[str]]:
    """
    keyword検索を実行してフィルタリング
    
    Returns:
        (keyword_results, before_filter_count, after_filter_count, sources_before)
    """
    keyword_results: Dict[Tuple[str, int, int], Tuple[str, int]] = {}
    keyword_before_filter = 0
    keyword_after_filter = 0
    keyword_sources_before = []
    
    try:
        # フィルタなしで取得
        scored_chunks_all = search_chunks(query, k=candidate_k, source_filter=None)
        keyword_before_filter = len(scored_chunks_all)
        keyword_sources_before = [chunk.source for chunk, _ in scored_chunks_all]
        
        # source_filter適用
        if source_filter:
            scored_chunks = [
                (chunk, score) for chunk, score in scored_chunks_all
                if unicodedata.normalize("NFC", chunk.source) in source_filter
            ]
        else:
            scored_chunks = scored_chunks_all
        
        keyword_after_filter = len(scored_chunks)
        
        # keyword_resultsに格納
        for rank, (chunk, raw_score) in enumerate(scored_chunks):
            key = (chunk.source, chunk.page, chunk.chunk_index)
            keyword_results[key] = (chunk.text, rank + 1)
        
        logger.info(
            f"keyword検索: before_filter={keyword_before_filter}, "
            f"after_filter={keyword_after_filter}, top3_raw_scores={[s for _, s in scored_chunks[:3]]}"
        )
    except Exception as e:
        logger.warning(f"Keyword検索に失敗: {type(e).__name__}: {e}")
    
    return (keyword_results, keyword_before_filter, keyword_after_filter, keyword_sources_before)


def _merge_with_rrf(
    semantic_results: Dict,
    keyword_results: Dict,
    semantic_weight: float,
    keyword_weight: float,
    candidate_k: int
) -> Dict[Tuple[str, int, int], Tuple[str, float, int, int]]:
    """
    RRF（Reciprocal Rank Fusion）でマージ
    
    Returns:
        rrf_results: {key: (text, rrf_score, rank_sem, rank_kw)}
    """
    rrf_results: Dict[Tuple[str, int, int], Tuple[str, float, int, int]] = {}
    
    all_keys = set(semantic_results.keys()) | set(keyword_results.keys())
    
    for key in all_keys:
        # textはsemanticを優先
        text = semantic_results.get(key, (None, 0))[0] or keyword_results.get(key, (None, 0))[0]
        
        # rankを取得
        rank_sem = semantic_results.get(key, (None, candidate_k + 100))[1]
        rank_kw = keyword_results.get(key, (None, candidate_k + 100))[1]
        
        # RRFスコア計算
        rrf_score = (
            semantic_weight / (settings.rrf_k + rank_sem) +
            keyword_weight / (settings.rrf_k + rank_kw)
        )
        
        rrf_results[key] = (text, rrf_score, rank_sem, rank_kw)
    
    return rrf_results


def _perform_reranking(
    query: str,
    sorted_rrf: List,
    rerank_n: int,
    top_k: int,
    include_debug: bool,
    source_filter: Optional[List[str]]
) -> Tuple[List[Citation], Optional[List[Dict]], int, int, List, List, List]:
    """
    Cross-Encoderでリランキング
    
    Returns:
        (citations, quiz_candidates, post_rerank_count, after_threshold_count,
         pre_rerank_info, post_rerank_info, post_rerank_with_text)
    """
    citations = []
    quiz_candidates = None
    pre_rerank_info = []
    post_rerank_info = []
    post_rerank_with_text = []
    post_rerank_count = 0
    after_threshold_count = 0
    
    if settings.rerank_enabled and len(sorted_rrf) > 0:
        rerank_candidates = sorted_rrf[:rerank_n]
        
        # Cross-Encoder用のドキュメントリスト作成
        documents_for_rerank = [
            (text, {"key": key, "rrf_score": rrf_score, "rank_sem": rank_sem, "rank_kw": rank_kw})
            for key, (text, rrf_score, rank_sem, rank_kw) in rerank_candidates
        ]
        
        # debug用: pre_rerank情報を記録
        if include_debug:
            for key, (text, rrf_score, rank_sem, rank_kw) in rerank_candidates:
                pre_rerank_info.append({
                    "source": key[0],
                    "page": key[1],
                    "rrf_score": round(rrf_score, 4),
                    "rank_sem": rank_sem,
                    "rank_kw": rank_kw,
                })
        
        try:
            # Cross-Encoderで再スコアリング
            reranked = rerank_documents(
                query=query,
                documents=documents_for_rerank,
                model_name=settings.rerank_model,
                top_n=None,
                batch_size=settings.rerank_batch_size,
            )
            
            post_rerank_count = len(reranked)
            
            # quiz_candidatesを常に作成
            quiz_candidates = []
            for text, metadata, rerank_score in reranked:
                key = metadata["key"]
                quiz_candidates.append({
                    "source": key[0],
                    "page": key[1],
                    "chunk_index": key[2],
                    "text": text,
                    "rerank_score": round(rerank_score, 4),
                    "rrf_score": round(metadata["rrf_score"], 4),
                })
            
            # debug用: post_rerank情報を記録
            if include_debug:
                for text, metadata, rerank_score in reranked:
                    key = metadata["key"]
                    post_rerank_info.append({
                        "source": key[0],
                        "page": key[1],
                        "rerank_score": round(rerank_score, 4),
                        "rrf_score": round(metadata["rrf_score"], 4),
                    })
                    post_rerank_with_text.append({
                        "source": key[0],
                        "page": key[1],
                        "chunk_index": key[2],
                        "text": text,
                        "rerank_score": round(rerank_score, 4),
                        "rrf_score": round(metadata["rrf_score"], 4),
                    })
            
            # 上位top_k件をcitationsとして作成
            seen_quotes: set = set()
            top_score = reranked[0][2] if len(reranked) > 0 else 0.0
            threshold_passed = 0
            
            for text, metadata, rerank_score in reranked[:top_k * 3]:
                key = metadata["key"]
                source, page, chunk_index = key
                
                # source_filter適用
                if source_filter and source not in source_filter:
                    logger.info(f"post_rerank source フィルタで除外: source={source}")
                    continue
                
                # 絶対値閾値でフィルタリング
                if rerank_score < settings.rerank_score_threshold:
                    logger.info(
                        f"Cross-Encoderスコア閾値（絶対値）で除外: source={source}, "
                        f"score={rerank_score:.4f} < {settings.rerank_score_threshold}"
                    )
                    continue
                
                # 相対的スコア差分でフィルタリング
                score_gap = top_score - rerank_score
                if score_gap > settings.rerank_score_gap_threshold:
                    logger.info(
                        f"Cross-Encoderスコア差分で除外: source={source}, "
                        f"top_score={top_score:.4f}, current_score={rerank_score:.4f}, "
                        f"gap={score_gap:.4f} > {settings.rerank_score_gap_threshold}"
                    )
                    continue
                
                threshold_passed += 1
                
                # 重複排除
                quote_prefix = text[:60].strip()
                quote_key = (source, page, quote_prefix)
                
                if quote_key not in seen_quotes:
                    seen_quotes.add(quote_key)
                    
                    page_value = page if page is not None and page > 0 else None
                    quote = text[:400] if len(text) > 400 else text
                    
                    citations.append(
                        Citation(
                            source=source,
                            page=page_value,
                            quote=quote,
                        )
                    )
                    
                    if len(citations) >= top_k:
                        break
            
            after_threshold_count = threshold_passed
            
            logger.info(
                f"Cross-Encoderリランキング: post_rerank={post_rerank_count}, "
                f"after_threshold={after_threshold_count}, final_citations={len(citations)}"
            )
            
        except Exception as e:
            logger.error(f"Cross-Encoderリランキングに失敗: {type(e).__name__}: {e}")
            citations = _create_citations_from_rrf(sorted_rrf, top_k)
            quiz_candidates = _create_quiz_candidates_from_rrf(sorted_rrf, settings.quiz_fallback_top_n)
    else:
        logger.info("Cross-Encoderリランキング無効: RRF順位を使用")
        citations = _create_citations_from_rrf(sorted_rrf, top_k)
        quiz_candidates = _create_quiz_candidates_from_rrf(sorted_rrf, settings.quiz_fallback_top_n)
    
    return (citations, quiz_candidates, post_rerank_count, after_threshold_count,
            pre_rerank_info, post_rerank_info, post_rerank_with_text)


def _create_citations_from_rrf(
    sorted_rrf: List[Tuple[Tuple[str, int, int], Tuple[str, float, int, int]]],
    top_k: int,
) -> List[Citation]:
    """RRF結果からcitationsを作成（リランキングなしのフォールバック）"""
    citations = []
    seen_quotes: set = set()
    
    for key, (text, rrf_score, rank_sem, rank_kw) in sorted_rrf[:top_k * 2]:
        source, page, chunk_index = key
        
        quote_prefix = text[:60].strip()
        quote_key = (source, page, quote_prefix)
        
        if quote_key not in seen_quotes:
            seen_quotes.add(quote_key)
            
            page_value = page if page is not None and page > 0 else None
            quote = text[:400] if len(text) > 400 else text
            
            citations.append(
                Citation(
                    source=source,
                    page=page_value,
                    quote=quote,
                )
            )
            
            if len(citations) >= top_k:
                break
    
    return citations


def _create_quiz_candidates_from_rrf(
    sorted_rrf: List[Tuple[Tuple[str, int, int], Tuple[str, float, int, int]]],
    top_n: int,
) -> List[Dict]:
    """RRF結果からquiz_candidatesを作成（リランキング失敗時のフォールバック）"""
    quiz_candidates = []
    
    for key, (text, rrf_score, rank_sem, rank_kw) in sorted_rrf[:top_n]:
        source, page, chunk_index = key
        
        quiz_candidates.append({
            "source": source,
            "page": page,
            "chunk_index": chunk_index,
            "text": text,
            "rerank_score": None,
            "rrf_score": round(rrf_score, 4),
        })
    
    return quiz_candidates


def _build_debug_info(
    collection_count: int,
    candidate_k: int,
    rerank_n: int,
    top_k: int,
    semantic_before_filter: int,
    semantic_after_filter: int,
    keyword_before_filter: int,
    keyword_after_filter: int,
    merged_count: int,
    post_rerank_count: int,
    after_threshold_count: int,
    final_citations_count: int,
    semantic_hits_count: int,
    keyword_hits_count: int,
    pre_rerank_info: List,
    post_rerank_info: List,
    post_rerank_with_text: List,
    citations: List[Citation],
    source_filter: Optional[List[str]],
    semantic_sources_before: List[str],
    keyword_sources_before: List[str]
) -> Dict:
    """debug情報を構築"""
    debug_info = {
        "collection_count": collection_count,
        "candidate_k": candidate_k,
        "rerank_n": rerank_n,
        "top_k": top_k,
        "semantic_before_filter": semantic_before_filter,
        "semantic_after_filter": semantic_after_filter,
        "keyword_before_filter": keyword_before_filter,
        "keyword_after_filter": keyword_after_filter,
        "merged_count": merged_count,
        "post_rerank_count": post_rerank_count,
        "after_threshold_count": after_threshold_count,
        "final_citations_count": final_citations_count,
        "semantic_hits_count": semantic_hits_count,
        "keyword_hits_count": keyword_hits_count,
        "pre_rerank": pre_rerank_info,
        "post_rerank": post_rerank_info,
        "final_selected_sources": [c.source for c in citations],
        "_post_rerank_with_text": post_rerank_with_text,
    }
    
    if source_filter:
        debug_info["allowed_sources"] = source_filter
        debug_info["filtered_collection_count"] = collection_count
        debug_info["semantic_sources_before_unique"] = sorted(set(semantic_sources_before))
        debug_info["keyword_sources_before_unique"] = sorted(set(keyword_sources_before))
    
    if final_citations_count == 0:
        reasons = []
        if semantic_after_filter == 0 and keyword_after_filter == 0:
            reasons.append("semantic_after_filter=0 and keyword_after_filter=0")
        elif merged_count == 0:
            reasons.append("merged_count=0")
        elif post_rerank_count == 0:
            reasons.append("post_rerank_count=0")
        elif after_threshold_count == 0:
            reasons.append("all_candidates_removed_by_rerank_threshold")
        else:
            reasons.append("merged_count>0 but final_citations_count=0 (dedup or other)")
        
        debug_info["zero_reason"] = " | ".join(reasons)
    
    return debug_info
