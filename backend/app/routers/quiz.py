"""
Quiz APIルーター
"""
import asyncio
from fastapi import APIRouter

from app.quiz.store import QuizItem, save_quiz
from app.schemas.quiz import QuizRequest, QuizResponse
from app.schemas.common import Citation

router = APIRouter()


@router.post("", response_model=QuizResponse)
async def create_quiz(request: QuizRequest) -> QuizResponse:
    """
    クイズを出題する（ダミー実装）

    - level: 必須。beginner/intermediate/advancedのいずれか
    """
    # ローディング確認用の遅延
    await asyncio.sleep(0.8)

    # levelに応じた問題文を生成（ダミー）
    level_texts = {
        "beginner": "初級",
        "intermediate": "中級",
        "advanced": "上級",
    }
    level_text = level_texts.get(request.level, "初級")
    question = f"○×：（ダミー）{level_text}レベルの問題です。最初にAを実行する。"

    # クイズアイテムを作成（正解はtrue固定）
    quiz_item = QuizItem(
        question=question,
        correct_answer=True,
        explanation="（ダミー）解説です。",
        citations=[
            Citation(
                source="dummy.txt",
                page=1,
                quote="（ダミー）引用です。",
            )
        ],
    )

    # storeに保存してquiz_idを取得
    quiz_id = save_quiz(quiz_item)

    # レスポンスを返す
    return QuizResponse(
        quiz_id=quiz_id,
        question=question,
    )
