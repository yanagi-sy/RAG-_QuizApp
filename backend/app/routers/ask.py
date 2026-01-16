"""
QA (Ask) APIルーター
"""
import asyncio
import logging
import re
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
from app.llm.base import LLMInternalError
from app.llm.base import LLMTimeoutError
from app.llm.ollama import get_ollama_client
from app.llm.prompt import build_messages

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


def normalize_question(question: str) -> str:
    """
    質問文を検索用クエリに正規化する（最低限の処理）
    
    - 改行 → 空白
    - 連続空白の圧縮
    - strip
    
    Args:
        question: 元の質問文
        
    Returns:
        正規化された検索クエリ
    """
    # 改行を空白に置換
    normalized = question.replace('\n', ' ').replace('\r', ' ')
    
    # 連続スペースを1つにまとめ、strip
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


@router.post("", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """
    質問を受け取り、回答を返す（hybrid retrieval実装）

    - question: 必須。空文字列や空白のみの場合はINVALID_INPUTエラー
    - retrieval: オプション。semantic_weight（0.0-1.0、デフォルト0.7）を指定可能
    """
    # ローディング確認用の遅延
    await asyncio.sleep(0.8)

    # バリデーション: 空文字列や空白のみはエラー
    if not request.question or not request.question.strip():
        raise_invalid_input("questionは必須です。空文字列や空白のみは許可されません。")

    # 質問文を正規化して検索用クエリに変換
    search_query = normalize_question(request.question)
    
    # 正規化後のクエリが空の場合は元の質問文を使用
    if not search_query:
        search_query = request.question.strip()

    # NEW: semantic_weightを取得（デフォルト0.7）
    semantic_weight = 0.7
    if request.retrieval is not None:
        semantic_weight = request.retrieval.semantic_weight
    keyword_weight = 1.0 - semantic_weight

    # CHANGED: Hybrid retrieval（semantic + keyword）でcitationsを作成
    citations = []
    debug_info = None
    try:
        citations, debug_info = _hybrid_retrieval(
            query=search_query,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            top_k=settings.top_k,
            include_debug=request.debug,  # NEW: debug情報を含めるかどうか
        )
    except Exception as e:
        # Hybrid retrieval失敗時もログだけ出して続行（citationsは空リスト）
        logger.warning(f"Hybrid retrievalに失敗しました: query='{search_query}', error={type(e).__name__}: {e}")

    # LLMで回答生成（retrieval-first）
    try:
        # プロンプトを構築
        messages = build_messages(request.question, citations)
        
        # Ollamaクライアントを取得して回答生成
        ollama_client = get_ollama_client()
        answer = await ollama_client.chat(messages)
        
        # 回答本文から番号参照を除去（根拠はcitationsで別表示されるため）  # CHANGED
        # 除去対象: "(根拠12)" "（根拠12）" "根拠12" "参照12" など
        answer = re.sub(r'[（(]?(根拠|参照)\d+[）)]?', '', answer)
        # 除去後の連続空白を1つにまとめる
        answer = re.sub(r'\s+', ' ', answer).strip()
        
        logger.info(f"回答生成成功: {len(answer)}文字")
    
    except (LLMTimeoutError, LLMInternalError) as e:
        # LLM失敗時もHTTP 200で返す（citationsは必ず返す）
        logger.warning(f"LLM呼び出し失敗: {type(e).__name__}: {e}")
        
        if len(citations) > 0:
            answer = "回答生成に失敗しました。根拠情報のみ表示します。"
        else:
            answer = "関連する情報が見つかりませんでした。質問を言い換えて再度お試しください。"
    
    except Exception as e:
        # 予期しないエラーも同じくHTTP 200で返す
        logger.error(f"予期しないエラー: {type(e).__name__}: {e}")
        
        if len(citations) > 0:
            answer = "回答生成に失敗しました。根拠情報のみ表示します。"
        else:
            answer = "関連する情報が見つかりませんでした。質問を言い換えて再度お試しください。"

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
    include_debug: bool = False,  # NEW: debug情報を含めるかどうか
) -> tuple[list[Citation], dict | None]:
    """
    Hybrid retrieval（semantic + keyword）でcitationsを作成
    
    Args:
        query: 検索クエリ
        semantic_weight: semantic検索の重み（0.0-1.0）
        keyword_weight: keyword検索の重み（0.0-1.0）
        top_k: 取得件数
        include_debug: debug情報を含めるかどうか
        
    Returns:
        (Citationのリスト, debug情報の辞書またはNone)のタプル
    """
    from typing import Dict, Tuple
    
    # NEW: collection_countを取得（debug情報用）
    collection_count = 0
    
    # CHANGED: debug_infoを最初に初期化（常にタプルを返すことを保証）
    debug_info: dict | None = None
    
    # NEW: semantic検索（既存のChroma queryを使用）
    semantic_results: Dict[Tuple[str, int, int], Tuple[str, float]] = {}
    semantic_hits = 0
    try:
        # 質問をEmbeddingに変換
        query_embedding = embed_query(query, model_name=settings.embedding_model)
        
        # ChromaDBから検索
        collection = get_vectorstore(settings.chroma_dir)
        
        # コレクションの件数をチェック
        collection_count = get_collection_count(collection)
        if collection_count == 0:
            logger.warning(
                f"Chroma collection is empty. Run build_index first. chroma_dir={settings.chroma_dir}"
            )
        
        documents, metadatas, distances = query_chunks(
            collection=collection,
            query_embedding=query_embedding,
            top_k=top_k * 2,  # マージ前に多めに取得
        )
        
        # distanceをscoreに変換（score = 1 - distance、0〜1にclamp）
        semantic_scores = []
        for dist in distances:
            score = max(0.0, min(1.0, 1.0 - dist))  # 0〜1にclamp
            semantic_scores.append(score)
        
        # semantic結果を辞書に格納（key: (source, page, chunk_index)）
        for doc_text, metadata, score in zip(documents, metadatas, semantic_scores):
            source = metadata.get("source", "")
            page = metadata.get("page", 0)
            chunk_index = metadata.get("chunk_index", 0)
            key = (source, page, chunk_index)
            semantic_results[key] = (doc_text, score)
            semantic_hits += 1
        
        # distances の先頭3件をログ出力（観測性）
        if distances:
            logger.info(f"semantic distances (top3): {distances[:3]}")
    except Exception as e:
        logger.warning(f"Semantic検索に失敗しました: {type(e).__name__}: {e}")
    
    # NEW: keyword検索（既存のsearch_chunksを使用）
    keyword_results: Dict[Tuple[str, int, int], Tuple[str, float]] = {}
    keyword_hits = 0
    try:
        # keyword検索を実行（kを多めに取得）
        scored_chunks = search_chunks(query, k=top_k * 2)
        
        if len(scored_chunks) > 0:
            # scoreを0〜1に正規化（min-max正規化）
            scores = [score for _, score in scored_chunks]
            if len(scores) > 0:
                min_score = min(scores)
                max_score = max(scores)
                score_range = max_score - min_score
                
                # keyword結果を辞書に格納（key: (source, page, chunk_index)）
                for chunk, raw_score in scored_chunks:
                    # min-max正規化（0〜1に変換）
                    if score_range > 0:
                        normalized_score = (raw_score - min_score) / score_range
                    else:
                        normalized_score = 1.0 if raw_score > 0 else 0.0
                    
                    key = (chunk.source, chunk.page, chunk.chunk_index)
                    keyword_results[key] = (chunk.text, normalized_score)
                    keyword_hits += 1
    except Exception as e:
        logger.warning(f"Keyword検索に失敗しました: {type(e).__name__}: {e}")
    
    # NEW: 両者をマージ（同一IDで統合、final_score = w*semantic + (1-w)*keyword）
    merged_results: Dict[Tuple[str, int, int], Tuple[str, float]] = {}
    
    # semantic結果をマージ
    for key, (text, score) in semantic_results.items():
        final_score = semantic_weight * score
        merged_results[key] = (text, final_score)
    
    # CHANGED: keyword結果をマージ（既存のkeyがあればスコアだけ加算、textは上書きしない）
    for key, (text, score) in keyword_results.items():
        if key in merged_results:
            # 既存のtextを維持し、スコアだけ加算（semanticのtextを優先）
            existing_text, existing_score = merged_results[key]
            merged_results[key] = (existing_text, existing_score + keyword_weight * score)
        else:
            # 新規追加
            merged_results[key] = (text, keyword_weight * score)
    
    # NEW: スコア降順でソート
    sorted_results = sorted(
        merged_results.items(),
        key=lambda x: x[1][1],  # (text, score)のscoreでソート
        reverse=True
    )
    
    # NEW: 重複排除（source, page, quote先頭60文字）とcitations作成
    seen_quotes: set[Tuple[str, int, str]] = set()
    citations = []
    
    for (source, page, chunk_index), (text, final_score) in sorted_results[:top_k * 2]:
        # quote先頭60文字で重複判定
        quote_prefix = text[:60].strip()
        quote_key = (source, page, quote_prefix)
        
        if quote_key not in seen_quotes:
            seen_quotes.add(quote_key)
            
            # pageの扱い：txtはnull、pdfは1以上をそのまま返す
            page_value = page if page is not None and page > 0 else None
            
            # CHANGED: quoteはAPIレスポンス時に最大400文字で切る（DBには全文保持、表示都合で短縮）
            quote = text[:400] if len(text) > 400 else text
            
            citations.append(
                Citation(
                    source=source,
                    page=page_value,
                    quote=quote,
                )
            )
            
            # top_k件に達したら終了
            if len(citations) >= top_k:
                break
    
    # NEW: 観測性ログ（semantic_hits/keyword_hits/merged_hits、top3のスコア一覧）
    merged_hits = len(merged_results)
    top3_scores = [score for _, (_, score) in sorted_results[:3]]
    logger.info(
        f"hybrid retrieval: semantic_hits={semantic_hits}, "
        f"keyword_hits={keyword_hits}, merged_hits={merged_hits}, "
        f"top3_scores={top3_scores}, final_citations={len(citations)}"
    )
    
    # CHANGED: debug情報を構築（include_debugがTrueの場合のみ、Falseの場合はNoneのまま）
    if include_debug:
        debug_info = {
            "semantic_weight": semantic_weight,
            "keyword_weight": keyword_weight,
            "semantic_hits": semantic_hits,
            "keyword_hits": keyword_hits,
            "merged_hits": merged_hits,
            "top3_scores": top3_scores,
            "collection_count": collection_count,
        }
    
    # CHANGED: 常にタプルを返す（debug_infoはNoneまたはdict）
    return citations, debug_info
