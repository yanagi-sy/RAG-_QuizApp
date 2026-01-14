"""
QA (Ask) APIルーター
"""
import asyncio
from fastapi import APIRouter

from app.core.errors import raise_invalid_input
from app.schemas.ask import AskRequest, AskResponse
from app.schemas.common import Citation

router = APIRouter()


@router.post("", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """
    質問を受け取り、回答を返す（ダミー実装）

    - question: 必須。空文字列や空白のみの場合はINVALID_INPUTエラー
    - retrieval: オプション。受け取るだけでOK（正規化処理は不要）
    """
    # ローディング確認用の遅延
    await asyncio.sleep(0.8)

    # バリデーション: 空文字列や空白のみはエラー
    if not request.question or not request.question.strip():
        raise_invalid_input("questionは必須です。空文字列や空白のみは許可されません。")

    # ダミーレスポンス（固定）
    return AskResponse(
        answer="（ダミー）これは回答です。",
        citations=[
            Citation(
                source="dummy.txt",
                page=1,
                quote="（ダミー）引用です。",
            )
        ],
    )
