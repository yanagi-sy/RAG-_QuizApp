"""
Search APIルーター
"""
from fastapi import APIRouter

from app.core.errors import raise_invalid_input
from app.schemas.search import SearchRequest, SearchResponse, Candidate
from app.search.index import search_chunks, create_snippet

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """
    チャンクを検索する（暫定実装）

    - query: 必須。空文字列や空白のみの場合はINVALID_INPUTエラー
    - k: 任意。1〜10、デフォルト5
    """
    # バリデーション: 空文字列や空白のみはエラー
    if not request.query or not request.query.strip():
        raise_invalid_input("検索クエリを入力してください")
    
    # 検索実行
    scored_chunks = search_chunks(request.query, request.k)
    
    # レスポンス形式に変換
    candidates = []
    for chunk, score in scored_chunks:
        # スニペット作成
        snippet = create_snippet(chunk.text, request.query)
        
        # pageはPDFの場合のみ設定（txtの場合はnull）
        page = chunk.page if chunk.page > 1 else None
        
        candidates.append(
            Candidate(
                source=chunk.source,
                page=page,
                snippet=snippet,
                score=score,
            )
        )
    
    return SearchResponse(candidates=candidates)
