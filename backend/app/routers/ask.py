"""
QA (Ask) APIルーター
"""
import asyncio
import logging
import re
from typing import Dict, Tuple, List
from fastapi import APIRouter

from app.core.errors import raise_invalid_input
from app.core.settings import settings
from app.schemas.ask import AskRequest
from app.schemas.ask import AskResponse
from app.schemas.common import Citation
from app.rag.embedding import embed_query
from app.rag.vectorstore import get_collection_count
from app.rag.vectorstore import get_vectorstore
from app.rag.vectorstore import query_chunks
from app.search.index import search_chunks  # NEW: keyword検索用
from app.search.reranker import rerank_documents  # NEW: Cross-Encoder
from app.llm.base import LLMInternalError
from app.llm.base import LLMTimeoutError
from app.llm.ollama import get_ollama_client
from app.llm.prompt import build_messages

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


def normalize_question(question: str) -> str:
    """
    質問文を正規化する

    Args:
        question: 質問文

    Returns:
        正規化された質問文
    """
    # 余計な空白を削除
    question = re.sub(r"\s+", " ", question).strip()
    return question


@router.post("", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """
    質問を受け取り、回答を返す

    Args:
        request: 質問リクエスト

    Returns:
        回答レスポンス
    """
    # 質問文の検証
    question = normalize_question(request.question)
    if not question:
        raise_invalid_input("質問文が空です")

    # 検索パラメータ
    semantic_weight = 0.7  # デフォルト
    if request.retrieval and request.retrieval.semantic_weight is not None:
        semantic_weight = request.retrieval.semantic_weight
        # 0.0〜1.0にclamp
        semantic_weight = max(0.0, min(1.0, semantic_weight))

    keyword_weight = 1.0 - semantic_weight

    # CHANGED: Hybrid retrieval（RRF + Cross-Encoder）でcitationsを作成
    citations = []
    debug_info = None
    try:
        citations, debug_info = _hybrid_retrieval(
            query=question,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            top_k=settings.top_k,
            include_debug=request.debug,  # NEW: debug情報を含めるかどうか
        )
    except Exception as e:
        # Hybrid retrieval失敗時もログだけ出して続行（citationsは空リスト）
        logger.warning(f"Hybrid retrievalに失敗しました: {type(e).__name__}: {e}")

    # LLMで回答生成を試みる
    answer = ""
    try:
        # LLMクライアントを取得
        llm_client = get_ollama_client()

        # プロンプトを構築
        messages = build_messages(
            question=question,
            citations=citations,
        )

        # LLMで回答生成
        answer = await asyncio.wait_for(
            llm_client.chat(messages=messages),
            timeout=settings.ollama_timeout_sec,
        )

    except (LLMTimeoutError, asyncio.TimeoutError):
        logger.warning("LLM回答生成がタイムアウトしました。citationsのみ返します。")
        answer = "回答生成がタイムアウトしました。根拠を参照してください。"
    except LLMInternalError as e:
        logger.warning(f"LLM回答生成に失敗しました: {e}。citationsのみ返します。")
        answer = "回答生成に失敗しました。根拠を参照してください。"
    except Exception as e:
        logger.error(f"予期しないエラー: {type(e).__name__}: {e}")
        answer = "予期しないエラーが発生しました。根拠を参照してください。"

    # レスポンスを返す
    return AskResponse(
        answer=answer,
        citations=citations,
        debug=debug_info if request.debug else None,  # NEW: debug=trueの場合のみdebug情報を返す
    )


def _hybrid_retrieval(
    query: str,
    semantic_weight: float,
    keyword_weight: float,
    top_k: int,
    include_debug: bool = False,
) -> tuple[list[Citation], dict | None]:
    """
    Hybrid retrieval（RRF融合 + Cross-Encoderリランキング）でcitationsを作成
    
    CHANGED: 従来のmin-max正規化+スコア加重和を廃止し、RRF順位融合+Cross-Encoderに変更
    
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
        
    Returns:
        (Citationのリスト, debug情報の辞書またはNone)のタプル
    """
    # NEW: debug_infoを最初に初期化（常にタプルを返すことを保証）
    debug_info: dict | None = None
    
    # NEW: 候補数を総チャンク数から動的に決定
    collection = get_vectorstore(settings.chroma_dir)
    collection_count = get_collection_count(collection)
    
    if collection_count == 0:
        logger.warning(f"Chroma collection is empty. Run build_index first.")
        return ([], debug_info)
    
    # candidate_k = clamp(round(collection_count * ratio), min_k, max_k)
    candidate_k = max(
        settings.candidate_min_k,
        min(
            settings.candidate_max_k,
            round(collection_count * settings.candidate_ratio)
        )
    )
    
    # rerank_n = clamp(round(candidate_k * ratio), min_n, max_n)
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
    
    # NEW: semantic検索（candidate_k件取得、順位を記録）
    semantic_results: Dict[Tuple[str, int, int], Tuple[str, int]] = {}  # key: (text, rank)
    try:
        query_embedding = embed_query(query, model_name=settings.embedding_model)
        documents, metadatas, distances = query_chunks(
            collection=collection,
            query_embedding=query_embedding,
            top_k=candidate_k,
        )
        
        for rank, (doc_text, metadata) in enumerate(zip(documents, metadatas)):
            source = metadata.get("source", "")
            page = metadata.get("page", 0)
            chunk_index = metadata.get("chunk_index", 0)
            key = (source, page, chunk_index)
            semantic_results[key] = (doc_text, rank + 1)  # rank is 1-based
        
        logger.info(f"semantic検索: {len(semantic_results)}件取得, distances_top3={distances[:3]}")
    except Exception as e:
        logger.warning(f"Semantic検索に失敗: {type(e).__name__}: {e}")
    
    # NEW: keyword検索（candidate_k件取得、順位を記録）
    keyword_results: Dict[Tuple[str, int, int], Tuple[str, int]] = {}  # key: (text, rank)
    try:
        scored_chunks = search_chunks(query, k=candidate_k)
        
        for rank, (chunk, raw_score) in enumerate(scored_chunks):
            key = (chunk.source, chunk.page, chunk.chunk_index)
            keyword_results[key] = (chunk.text, rank + 1)  # rank is 1-based
        
        logger.info(f"keyword検索: {len(keyword_results)}件取得, top3_raw_scores={[s for _, s in scored_chunks[:3]]}")
    except Exception as e:
        logger.warning(f"Keyword検索に失敗: {type(e).__name__}: {e}")
    
    # NEW: RRF（Reciprocal Rank Fusion）でマージ
    # rrf_score = w_sem / (RRF_K + rank_sem) + w_kw / (RRF_K + rank_kw)
    rrf_results: Dict[Tuple[str, int, int], Tuple[str, float, int, int]] = {}  # key: (text, rrf_score, rank_sem, rank_kw)
    
    all_keys = set(semantic_results.keys()) | set(keyword_results.keys())
    
    for key in all_keys:
        # textはsemanticを優先、なければkeywordから取得
        text = semantic_results.get(key, (None, 0))[0] or keyword_results.get(key, (None, 0))[0]
        
        # rankを取得（ヒットしていない場合は大きな値）
        rank_sem = semantic_results.get(key, (None, candidate_k + 100))[1]
        rank_kw = keyword_results.get(key, (None, candidate_k + 100))[1]
        
        # RRFスコア計算
        rrf_score = (
            semantic_weight / (settings.rrf_k + rank_sem) +
            keyword_weight / (settings.rrf_k + rank_kw)
        )
        
        rrf_results[key] = (text, rrf_score, rank_sem, rank_kw)
    
    # RRFスコア降順でソート
    sorted_rrf = sorted(
        rrf_results.items(),
        key=lambda x: x[1][1],  # rrf_scoreでソート
        reverse=True
    )
    
    logger.info(
        f"RRF融合: merged={len(rrf_results)}件, "
        f"top3_rrf_scores={[score for _, (_, score, _, _) in sorted_rrf[:3]]}"
    )
    
    # NEW: 上位rerank_n件をCross-Encoderで再スコアリング
    citations = []
    pre_rerank_info = []  # debug用
    post_rerank_info = []  # debug用
    
    if settings.rerank_enabled and len(sorted_rrf) > 0:
        # rerank_n件を取得
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
                top_n=None,  # 全件再スコアリング
                batch_size=settings.rerank_batch_size,
            )
            
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
            
            # 上位top_k件をcitationsとして作成
            # NEW: 普遍的な品質管理（トップスコアとの相対的な差分）
            seen_quotes: set[Tuple[str, int, str]] = set()
            top_score = reranked[0][2] if len(reranked) > 0 else 0.0  # NEW: トップスコアを取得
            
            for text, metadata, rerank_score in reranked[:top_k * 3]:  # CHANGED: 閾値フィルタ分多めに取得
                # NEW: 絶対値閾値でフィルタリング（基本品質保証）
                if rerank_score < settings.rerank_score_threshold:
                    logger.info(
                        f"Cross-Encoderスコア閾値（絶対値）で除外: source={metadata['key'][0]}, "
                        f"score={rerank_score:.4f} < {settings.rerank_score_threshold}"
                    )
                    continue
                
                # NEW: 相対的スコア差分でフィルタリング（普遍的な品質管理）
                score_gap = top_score - rerank_score
                if score_gap > settings.rerank_score_gap_threshold:
                    logger.info(
                        f"Cross-Encoderスコア差分で除外: source={metadata['key'][0]}, "
                        f"top_score={top_score:.4f}, current_score={rerank_score:.4f}, "
                        f"gap={score_gap:.4f} > {settings.rerank_score_gap_threshold}"
                    )
                    continue
                
                key = metadata["key"]
                source, page, chunk_index = key
                
                # 重複排除（source, page, quote先頭60文字）
                quote_prefix = text[:60].strip()
                quote_key = (source, page, quote_prefix)
                
                if quote_key not in seen_quotes:
                    seen_quotes.add(quote_key)
                    
                    # pageの扱い：txtはnull、pdfは1以上をそのまま返す
                    page_value = page if page is not None and page > 0 else None
                    
                    # quoteはAPIレスポンス時に最大400文字で切る
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
            
            logger.info(f"Cross-Encoderリランキング: final_citations={len(citations)}")
            
        except Exception as e:
            logger.error(f"Cross-Encoderリランキングに失敗: {type(e).__name__}: {e}")
            # フォールバック: RRFの順位をそのまま使用
            citations = _create_citations_from_rrf(sorted_rrf, top_k)
    else:
        # リランキング無効時: RRFの順位をそのまま使用
        logger.info("Cross-Encoderリランキング無効: RRF順位を使用")
        citations = _create_citations_from_rrf(sorted_rrf, top_k)
    
    # NEW: debug情報を構築
    if include_debug:
        debug_info = {
            "collection_count": collection_count,
            "candidate_k": candidate_k,
            "rerank_n": rerank_n,
            "top_k": top_k,
            "semantic_hits_count": len(semantic_results),
            "keyword_hits_count": len(keyword_results),
            "merged_count": len(rrf_results),
            "pre_rerank": pre_rerank_info,
            "post_rerank": post_rerank_info,
            "final_selected_sources": [c.source for c in citations],
        }
    
    return (citations, debug_info)


def _create_citations_from_rrf(
    sorted_rrf: List[Tuple[Tuple[str, int, int], Tuple[str, float, int, int]]],
    top_k: int,
) -> list[Citation]:
    """
    RRF結果からcitationsを作成（リランキングなしのフォールバック）
    
    Args:
        sorted_rrf: RRFでソート済みの結果
        top_k: 取得件数
        
    Returns:
        Citationのリスト
    """
    citations = []
    seen_quotes: set[Tuple[str, int, str]] = set()
    
    for key, (text, rrf_score, rank_sem, rank_kw) in sorted_rrf[:top_k * 2]:
        source, page, chunk_index = key
        
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
    
    return citations
