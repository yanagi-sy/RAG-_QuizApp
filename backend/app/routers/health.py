"""
Health check APIルーター
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health_check():
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}
