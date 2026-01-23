"""
Quiz専用: retrieveを「検索」から「サンプル取得」に変更

/ask とは完全に独立した、クイズ生成に特化したサンプリング処理。
- 抽象クエリの関連性やrerank閾値で 0件にならない設計
- source → chunk pool → sample → level別フィルタ → citations
"""
import logging
import time
import unicodedata
from typing import List, Dict, Optional, Tuple

from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore
from app.schemas.common import Citation
from app.quiz.chunk_pool import get_pool, sample_ids, sample_ids_multi_source, get_ids_for_source
from app.quiz.chunk_selector import select_chunks

# ロガー設定
logger = logging.getLogger(__name__)


def retrieve_for_quiz(
    source_ids: Optional[List[str]],
    level: str,
    count: int,
    debug: bool = False
) -> Tuple[List[Citation], Optional[Dict]]:
    """
    Quiz生成用の citations をサンプリングで取得
    
    検索ではなく「出題点サンプリング」:
    1. source が指定されていればその pool から ids を多めにサンプル
       指定なしなら複数 source から均等にサンプル
    2. collection.get(ids=sampled_ids) で chunk本文取得
    3. chunk_selector で levelに合う top_k を選ぶ
    4. citations を作る（最低 CIT_MIN=3 は確保）
    
    Args:
        source_ids: 対象source（Noneなら全資料対象）
        level: 難易度 (beginner / intermediate / advanced)
        count: 生成クイズ数（サンプル数の目安）
        debug: debug情報を返すか
        
    Returns:
        (citations, debug_info) のタプル
    """
    t_start = time.perf_counter()
    
    # collection を取得
    collection = get_vectorstore(settings.chroma_dir)
    
    # chunk pool を取得（lazy build）
    pool = get_pool(collection)
    
    if len(pool) == 0:
        logger.error("[QuizRetrieval] chunk pool が空です")
        return ([], {"error": "chunk pool が空です"})
    
    # source_ids を NFC 正規化
    if source_ids:
        source_ids = [unicodedata.normalize("NFC", s) for s in source_ids]
        logger.info(f"[QuizRetrieval] source_ids を NFC 正規化: {source_ids}")
    
    # サンプル数を決定（settings から取得）
    sample_n = max(count * settings.quiz_sample_multiplier, settings.quiz_sample_min_n)
    
    # 最低引用数（settings から取得）
    cit_min = settings.quiz_citations_min
    
    # IDをサンプリング
    if source_ids:
        # 指定sourceから均等にサンプル
        sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
    else:
        # 全sourceから均等にサンプル
        sampled_ids = sample_ids_multi_source(pool, None, sample_n)
    
    if len(sampled_ids) == 0:
        logger.error("[QuizRetrieval] サンプルIDが0件です")
        return ([], {"error": "サンプルIDが0件です", "quiz_pool_sources": list(pool.keys())})
    
    logger.info(f"[QuizRetrieval] {len(sampled_ids)}件のIDをサンプル")
    
    # chunkを取得（sourceフィルタを事前に適用）
    try:
        # 【品質担保】source_idsが指定されている場合、where条件でフィルタ
        # ChromaDBのwhere条件でsourceフィルタを適用（取得前にフィルタ）
        where_filter = None
        if source_ids and len(source_ids) > 0:
            # source_idsをNFC正規化（既に正規化済みだが念のため）
            source_ids_norm = [unicodedata.normalize("NFC", s) for s in source_ids]
            where_filter = {"source": {"$in": source_ids_norm}}
            logger.info(f"[QuizRetrieval] sourceフィルタを適用: {source_ids_norm}")
        
        results = collection.get(
            ids=sampled_ids,
            include=["documents", "metadatas"],
            where=where_filter  # ChromaDBのwhere条件でフィルタ
        )
    except Exception as e:
        logger.error(f"[QuizRetrieval] collection.get失敗: {type(e).__name__}: {e}")
        return ([], {"error": f"collection.get失敗: {str(e)}"})
    
    ids = results.get("ids", [])
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    
    if len(documents) == 0:
        logger.error("[QuizRetrieval] chunkが0件です")
        return ([], {"error": "chunkが0件です"})
    
    # 【品質担保】取得後のchunkのsourceを確認（フィルタが正しく機能しているか検証）
    if source_ids and len(source_ids) > 0:
        source_counts = {}
        for meta in metadatas:
            chunk_source = meta.get("source", "unknown")
            chunk_source_norm = unicodedata.normalize("NFC", chunk_source)
            source_counts[chunk_source] = source_counts.get(chunk_source, 0) + 1
            
            # 指定source以外のchunkが混入していないかチェック
            if chunk_source_norm not in source_ids:
                logger.error(
                    f"[QuizRetrieval] 【重大】指定source以外のchunkが混入: "
                    f"source={chunk_source} (norm={chunk_source_norm}), "
                    f"expected={source_ids}, chunk_id={ids[metadatas.index(meta)] if metadatas.index(meta) < len(ids) else 'N/A'}"
                )
        
        logger.info(f"[QuizRetrieval] {len(documents)}件のchunkを取得（source分布: {source_counts}）")
    else:
        logger.info(f"[QuizRetrieval] {len(documents)}件のchunkを取得")
    
    # chunk_selector で levelに合う chunk を選択
    # まずは cit_min * 2 件選択（余裕を持たせる）
    select_n = max(cit_min * 2, count * 2)
    
    chunks = [
        {"id": chunk_id, "document": doc, "metadata": meta}
        for chunk_id, doc, meta in zip(ids, documents, metadatas)
    ]
    
    selected_chunks = select_chunks(chunks, level, select_n)
    
    # citationsを作成（最低 CIT_MIN 件）
    citations = []
    seen_quotes = set()
    
    for chunk in selected_chunks:
        text = chunk["document"]
        metadata = chunk["metadata"]
        source = metadata.get("source", "unknown")
        page = metadata.get("page", 0)
        
        # 重複排除（source, page, quote先頭60文字）
        quote_prefix = text[:60].strip()
        quote_key = (source, page, quote_prefix)
        
        if quote_key not in seen_quotes:
            seen_quotes.add(quote_key)
            
            # pageの扱い：txtはnull、pdfは1以上をそのまま返す
            page_value = page if page is not None and page > 0 else None
            
            # quoteを quiz_quote_max_len で切る（デフォルト200文字）
            max_len = settings.quiz_quote_max_len
            quote = text[:max_len] if len(text) > max_len else text
            
            citations.append(
                Citation(
                    source=source,
                    page=page_value,
                    quote=quote,
                )
            )
    
    # citations が cit_min 未満なら再取得（最大2回）
    retry_count = 0
    max_retries = 2
    
    while len(citations) < cit_min and retry_count < max_retries:
        retry_count += 1
        logger.warning(f"[QuizRetrieval] citations不足({len(citations)}件 < {cit_min}), 再取得{retry_count}回目")
        
        # sample_n を増やして再サンプル
        sample_n = sample_n * 2
        
        if source_ids:
            sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
        else:
            sampled_ids = sample_ids_multi_source(pool, None, sample_n)
        
        if len(sampled_ids) == 0:
            break
        
        # chunk取得（sourceフィルタを事前に適用）
        try:
            # 【品質担保】source_idsが指定されている場合、where条件でフィルタ
            where_filter = None
            if source_ids and len(source_ids) > 0:
                source_ids_norm = [unicodedata.normalize("NFC", s) for s in source_ids]
                where_filter = {"source": {"$in": source_ids_norm}}
            
            results = collection.get(
                ids=sampled_ids,
                include=["documents", "metadatas"],
                where=where_filter  # ChromaDBのwhere条件でフィルタ
            )
        except Exception as e:
            logger.error(f"[QuizRetrieval] 再取得失敗: {type(e).__name__}: {e}")
            break
        
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        
        if len(documents) == 0:
            break
        
        # chunk_selector で選択
        chunks = [
            {"id": chunk_id, "document": doc, "metadata": meta}
            for chunk_id, doc, meta in zip(ids, documents, metadatas)
        ]
        
        selected_chunks = select_chunks(chunks, level, select_n * 2)
        
        # citations追加（重複排除）
        for chunk in selected_chunks:
            text = chunk["document"]
            metadata = chunk["metadata"]
            source = metadata.get("source", "unknown")
            page = metadata.get("page", 0)
            
            quote_prefix = text[:60].strip()
            quote_key = (source, page, quote_prefix)
            
            if quote_key not in seen_quotes:
                seen_quotes.add(quote_key)
                
                page_value = page if page is not None and page > 0 else None
                max_len = settings.quiz_quote_max_len
                quote = text[:max_len] if len(text) > max_len else text
                
                citations.append(
                    Citation(
                        source=source,
                        page=page_value,
                        quote=quote,
                    )
                )
                
                # cit_min に達したら終了
                if len(citations) >= cit_min:
                    break
    
    t_total_ms = (time.perf_counter() - t_start) * 1000
    
    logger.info(f"[QuizRetrieval] citations作成完了: {len(citations)}件, {round(t_total_ms, 1)}ms")
    
    # debug情報を構築
    debug_info = None
    if debug:
        # pool情報
        if source_ids:
            pool_sources = [s for s in source_ids if s in pool]
            pool_size = sum(len(get_ids_for_source(pool, s)) for s in pool_sources)
        else:
            pool_sources = list(pool.keys())
            pool_size = sum(len(ids) for ids in pool.values())
        
        debug_info = {
            "quiz_pool_sources": pool_sources,
            "quiz_pool_size": pool_size,
            "quiz_sample_n": sample_n,
            "quiz_selected_n": len(selected_chunks),
            "quiz_final_citations_count": len(citations),
            "quiz_level": level,
            "quiz_level_rules": f"{level}_keywords",
            "quiz_sources_unique": sorted(set(c.source for c in citations)),
            "quiz_retrieval_retry_count": retry_count,
        }
    
    return (citations, debug_info)
