"""
Quiz専用 Retrieval（検索ではなくサンプリングで根拠を取得）

【初心者向け】
- /ask とは別。クイズ用は「質問で検索」せず、指定資料からチャンクをランダムサンプル
- 流れ: Chunk Pool → 指定sourceからIDをサンプル → collection.get で本文取得
  → chunk_selector で難易度フィルタ → citations 作成（最低CIT_MIN件確保）
- source_ids は1件必須（routerで検証済み）。Unicode NFC正規化で比較
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
    
    # 【品質担保】source_idsは必ず1件が指定されている前提（routerで検証済み）
    if source_ids is None or len(source_ids) == 0:
        logger.error("[QuizRetrieval] source_idsが未指定です（routerで検証済みのため通常発生しません）")
        return ([], {"error": "source_idsが未指定です"})
    
    if len(source_ids) >= 2:
        logger.error(f"[QuizRetrieval] source_idsが複数指定されています（{len(source_ids)}件、routerで検証済みのため通常発生しません）")
        return ([], {"error": f"source_idsは1件のみ指定可能です（{len(source_ids)}件指定されています）"})
    
    # source_ids を NFC 正規化（1件のみ）
    source_ids = [unicodedata.normalize("NFC", source_ids[0])]
    target_source = unicodedata.normalize("NFC", source_ids[0])  # 明示的にNFC正規化
    logger.info(f"[QuizRetrieval] 単一ソース指定: source={target_source} (NFC正規化済み)")
    
    # サンプル数を決定（settings から取得）
    sample_n = max(count * settings.quiz_sample_multiplier, settings.quiz_sample_min_n)
    
    # 最低引用数（settings から取得）
    cit_min = settings.quiz_citations_min
    
    # 【品質担保】指定sourceのみからサンプル（他ソースは除外）
    sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
    
    # フィルタ後0件なら「根拠不足」で終了（他ソースへフォールバックしない）
    if len(sampled_ids) == 0:
        # poolのキーを確認してデバッグ情報を出力
        pool_keys = list(pool.keys())[:10]
        logger.error(
            f"[QuizRetrieval] 指定ソース '{target_source}' からサンプルIDが0件です（根拠不足）。"
            f"poolのキー: {pool_keys}"
        )
        return ([], {"error": f"指定ソース '{target_source}' から根拠が見つかりませんでした"})
    
    # 【デバッグ】サンプルされたIDのsourceを確認（実際に取得して確認）
    try:
        sample_results = collection.get(
            ids=sampled_ids[:10],  # 最初の10件のみ確認
            include=["metadatas"]
        )
        sample_sources = {}
        for meta in sample_results.get("metadatas", []):
            src = meta.get("source", "unknown")
            sample_sources[src] = sample_sources.get(src, 0) + 1
        logger.info(f"[QuizRetrieval] サンプルされたIDのsource分布（最初の10件）: {sample_sources}")
    except Exception as e:
        logger.warning(f"[QuizRetrieval] サンプルIDのsource確認に失敗: {e}")
    
    logger.info(f"[QuizRetrieval] {len(sampled_ids)}件のIDをサンプル（source={target_source}）")
    
    # 【品質担保】サンプルされたIDが0件の場合はエラーを返す
    if len(sampled_ids) == 0:
        logger.error(
            f"[QuizRetrieval] サンプルIDが0件です。"
            f"target_source={target_source}, pool_keys={list(pool.keys())[:10]}"
        )
        return ([], {"error": f"指定ソース '{target_source}' からサンプルIDが0件です（根拠不足）"})
    
    # chunkを取得
    try:
        results = collection.get(
            ids=sampled_ids,
            include=["documents", "metadatas"]
        )
    except Exception as e:
        logger.error(f"[QuizRetrieval] collection.get失敗: {type(e).__name__}: {e}")
        return ([], {"error": f"collection.get失敗: {str(e)}"})
    
    ids = results.get("ids", [])
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    
    if len(documents) == 0:
        logger.error(f"[QuizRetrieval] chunkが0件です（source={target_source}）")
        return ([], {"error": f"指定ソース '{target_source}' からchunkが0件です（根拠不足）"})
    
    # 【品質担保】指定source以外のchunkを除外
    filtered_chunks = []
    source_counts = {}  # デバッグ用：各sourceのchunk数をカウント
    target_source_norm = unicodedata.normalize("NFC", target_source)  # 事前に正規化
    
    for chunk_id, doc, meta in zip(ids, documents, metadatas):
        chunk_source = meta.get("source", "unknown")
        # Unicode正規化して比較（NFC正規化）
        chunk_source_norm = unicodedata.normalize("NFC", chunk_source)
        
        # デバッグ用：sourceをカウント
        source_counts[chunk_source] = source_counts.get(chunk_source, 0) + 1
        
        if chunk_source_norm == target_source_norm:
            filtered_chunks.append((chunk_id, doc, meta))
        else:
            # 【重大】ソース不一致のchunkが検出された場合はエラーログを出力
            logger.error(
                f"[QuizRetrieval] 【重大】ソース不一致のchunkを検出: "
                f"source={chunk_source} (norm={chunk_source_norm}) "
                f"target={target_source} (norm={target_source_norm}), "
                f"chunk_id={chunk_id}, quote_preview={doc[:50] if doc else 'N/A'}..."
            )
    
    # デバッグログ：取得されたchunkのsource分布を出力
    if len(filtered_chunks) == 0:
        logger.error(
            f"[QuizRetrieval] 指定ソース '{target_source}' に一致するchunkが0件です（根拠不足）。"
            f"取得されたchunkのsource分布: {source_counts}"
        )
        return ([], {"error": f"指定ソース '{target_source}' に一致するchunkが0件です（根拠不足）"})
    
    ids = [c[0] for c in filtered_chunks]
    documents = [c[1] for c in filtered_chunks]
    metadatas = [c[2] for c in filtered_chunks]
    
    logger.info(f"[QuizRetrieval] {len(documents)}件のchunkを取得（source={target_source}、フィルタ後）")
    
    # 【デバッグ】フィルタ後のchunkのsourceを確認
    filtered_sources = {}
    for meta in metadatas:
        src = meta.get("source", "unknown")
        filtered_sources[src] = filtered_sources.get(src, 0) + 1
    logger.info(f"[QuizRetrieval] フィルタ後のchunkのsource分布: {filtered_sources}")
    
    # chunk_selector で levelに合う chunk を選択
    # まずは cit_min * 2 件選択（余裕を持たせる）
    select_n = max(cit_min * 2, count * 2)
    
    chunks = [
        {"id": chunk_id, "document": doc, "metadata": meta}
        for chunk_id, doc, meta in zip(ids, documents, metadatas)
    ]
    
    selected_chunks = select_chunks(chunks, level, select_n)
    
    # 【デバッグ】選択後のchunkのsourceを確認
    selected_sources = {}
    for chunk in selected_chunks:
        src = chunk["metadata"].get("source", "unknown")
        selected_sources[src] = selected_sources.get(src, 0) + 1
    logger.info(f"[QuizRetrieval] chunk_selector選択後のsource分布: {selected_sources}")
    
    # citationsを作成（最低 CIT_MIN 件）
    citations = []
    seen_quotes = set()
    target_source_norm = unicodedata.normalize("NFC", target_source)  # 事前に正規化
    
    for chunk in selected_chunks:
        text = chunk["document"]
        metadata = chunk["metadata"]
        source = metadata.get("source", "unknown")
        page = metadata.get("page", 0)
        
        # 【品質担保】指定source以外のchunkを除外（念のため二重チェック）
        # Unicode正規化して比較
        source_norm = unicodedata.normalize("NFC", source)
        
        if source_norm != target_source_norm:
            logger.error(
                f"[QuizRetrieval] citations作成時にソース不一致を検出（重大）: "
                f"source={source} (norm={source_norm}) "
                f"target={target_source} (norm={target_source_norm}), "
                f"quote_preview={text[:50]}..."
            )
            continue
        
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
        
        # sample_n を増やして再サンプル（指定sourceのみ）
        sample_n = sample_n * 2
        sampled_ids = sample_ids_multi_source(pool, source_ids, sample_n)
        
        if len(sampled_ids) == 0:
            logger.error(f"[QuizRetrieval] 再取得でもサンプルIDが0件です（source={target_source}）")
            break
        
        # chunk取得
        try:
            results = collection.get(
                ids=sampled_ids,
                include=["documents", "metadatas"]
            )
        except Exception as e:
            logger.error(f"[QuizRetrieval] 再取得失敗: {type(e).__name__}: {e}")
            break
        
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        
        if len(documents) == 0:
            break
        
        # 【品質担保】指定source以外のchunkを除外
        filtered_chunks = []
        source_counts_retry = {}  # デバッグ用：各sourceのchunk数をカウント
        target_source_norm = unicodedata.normalize("NFC", target_source)  # 事前に正規化
        
        for chunk_id, doc, meta in zip(ids, documents, metadatas):
            chunk_source = meta.get("source", "unknown")
            # Unicode正規化して比較（NFC正規化）
            chunk_source_norm = unicodedata.normalize("NFC", chunk_source)
            
            # デバッグ用：sourceをカウント
            source_counts_retry[chunk_source] = source_counts_retry.get(chunk_source, 0) + 1
            
            if chunk_source_norm == target_source_norm:
                filtered_chunks.append((chunk_id, doc, meta))
            else:
                # デバッグログ：正規化前後の値を出力
                logger.debug(
                    f"[QuizRetrieval] 再取得時のソース不一致: "
                    f"source={chunk_source} (norm={chunk_source_norm}) "
                    f"target={target_source} (norm={target_source_norm})"
                )
        
        if len(filtered_chunks) == 0:
            logger.error(
                f"[QuizRetrieval] 再取得でも指定ソース '{target_source}' に一致するchunkが0件です。"
                f"取得されたchunkのsource分布: {source_counts_retry}"
            )
            break
        
        ids = [c[0] for c in filtered_chunks]
        documents = [c[1] for c in filtered_chunks]
        metadatas = [c[2] for c in filtered_chunks]
        
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
            
            # 【品質担保】指定source以外のchunkを除外（念のため二重チェック）
            # Unicode正規化して比較
            source_norm = unicodedata.normalize("NFC", source)
            target_source_norm = unicodedata.normalize("NFC", target_source)
            
            if source_norm != target_source_norm:
                logger.warning(
                    f"[QuizRetrieval] 再取得時のcitations作成でソース不一致を検出: "
                    f"source={source} (norm={source_norm}) "
                    f"target={target_source} (norm={target_source_norm})"
                )
                continue
            
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
    
    # 【デバッグ】最終的なcitationsのsource分布を確認
    final_citation_sources = {}
    for c in citations:
        final_citation_sources[c.source] = final_citation_sources.get(c.source, 0) + 1
    logger.info(
        f"[QuizRetrieval] 最終的なcitationsのsource分布: {final_citation_sources}, "
        f"expected={target_source}"
    )
    
    # 【品質担保】citationsに異なるsourceが含まれている場合は警告
    if len(final_citation_sources) > 1:
        logger.error(
            f"[QuizRetrieval] 重大: citationsに複数のsourceが含まれています: {final_citation_sources}, "
            f"expected={target_source}"
        )
    elif len(final_citation_sources) == 1:
        actual_source = list(final_citation_sources.keys())[0]
        # Unicode正規化して比較（NFC正規化）
        actual_source_norm = unicodedata.normalize("NFC", actual_source)
        target_source_norm = unicodedata.normalize("NFC", target_source)
        if actual_source_norm != target_source_norm:
            logger.error(
                f"[QuizRetrieval] 重大: citationsのsourceが指定ソースと一致しません: "
                f"actual={actual_source} (norm={actual_source_norm}), expected={target_source} (norm={target_source_norm})"
            )
    
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
