"""
FastAPIアプリケーションのエントリーポイント

実行方法:
    venv有効化後:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.routers import ask, quiz, judge, health, docs

app = FastAPI(
    title="RAG Quiz App API",
    description="QA and Quiz API",
    version="0.1.0",
)

# CORS設定: 環境変数から読み込む
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(ask.router, prefix="/ask", tags=["ask"])
app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])
app.include_router(judge.router, prefix="/judge", tags=["judge"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {"message": "RAG Quiz App API"}
