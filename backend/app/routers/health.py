"""
Health check APIルーター（死活確認用）

【初心者向け】
- GET /health: サーバーが生きているか確認するだけのエンドポイント
- ロードバランサーや監視ツールからよく叩かれる
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health_check():
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}
