"""
Judge APIルーター
"""
import asyncio
from fastapi import APIRouter

from app.core.errors import raise_not_found
from app.quiz.store import get_quiz
from app.schemas.judge import JudgeRequest, JudgeResponse

router = APIRouter()


@router.post("", response_model=JudgeResponse)
async def judge_answer(request: JudgeRequest) -> JudgeResponse:
    """
    回答を判定する（ダミー実装）

    - quiz_id: 必須。storeに存在しない場合はNOT_FOUNDエラー（HTTP 404 + JSON）
    - answer: 必須。true=○、false=×
    
    エラーレスポンス形式:
    {
      "error": {
        "code": "NOT_FOUND",
        "message": "クイズ情報が見つかりません。再出題してください。"
      }
    }
    """
    # ローディング確認用の遅延
    await asyncio.sleep(0.8)

    # storeからクイズを取得
    quiz_item = get_quiz(request.quiz_id)
    
    if quiz_item is None:
        # クイズが見つからない場合
        # raise_not_found は HTTP 404 と { "error": { "code": "NOT_FOUND", "message": "..." } } を返す
        raise_not_found("クイズ情報が見つかりません。再出題してください。")

    # 正誤判定（answerとcorrect_answerを比較）
    is_correct = request.answer == quiz_item.correct_answer

    # レスポンスを返す（storeの内容を使用）
    return JudgeResponse(
        is_correct=is_correct,
        correct_answer=quiz_item.correct_answer,
        explanation=quiz_item.explanation,
        citations=quiz_item.citations,
    )
