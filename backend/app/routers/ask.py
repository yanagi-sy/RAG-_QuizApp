"""
QA (Ask) APIルーター
"""
import asyncio
import re
from fastapi import APIRouter

from app.core.errors import raise_invalid_input
from app.schemas.ask import AskRequest, AskResponse
from app.schemas.common import Citation
from app.search.index import search_chunks, create_quote

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
    質問を受け取り、回答を返す（retrieval-first実装）

    - question: 必須。空文字列や空白のみの場合はINVALID_INPUTエラー
    - retrieval: オプション。将来用に受け取るだけ（現在は使用しない）
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

    # 検索実行（上位5件を取得）
    scored_chunks = search_chunks(search_query, k=5)

    # citationsを作成（重複排除付き）
    citations = []
    seen_keys = set()  # 重複判定用: (source, page, quote先頭60文字)
    
    for chunk, score in scored_chunks:
        # quoteを作成（240文字程度、クエリ近傍を優先）
        quote = create_quote(chunk, query=search_query, max_length=240)
        
        # pageの扱い：txtはnull、pdfは1以上をそのまま返す
        page = chunk.page if chunk.page is not None else None
        
        # 重複判定キー（source, page, quoteの先頭60文字）
        quote_key = quote[:60] if len(quote) > 60 else quote
        dedup_key = (chunk.source, page, quote_key)
        
        # 重複していない場合のみ追加
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            citations.append(
                Citation(
                    source=chunk.source,
                    page=page,
                    quote=quote,
                )
            )
            
            # 最大5件まで
            if len(citations) >= 5:
                break

    # 暫定の回答（固定文）
    if len(citations) > 0:
        answer = "見つかった根拠を提示します。必要なら質問を言い換えてください。"
    else:
        answer = "関連する情報が見つかりませんでした。質問を言い換えて再度お試しください。"

    return AskResponse(
        answer=answer,
        citations=citations,
    )
