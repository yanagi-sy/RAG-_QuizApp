"""
FastAPIアプリケーションのエントリーポイント

実行方法:
    venv有効化後:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.routers import ask, quiz, judge, health, docs, search
from app.rag.indexer import build_index  # NEW

# ロガー設定
logger = logging.getLogger(__name__)

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
app.include_router(search.router, prefix="/search", tags=["search"])


@app.on_event("startup")  # NEW: 起動時にインデックス作成
async def startup_event():
    """起動時の処理（インデックス作成）"""
    # NEW: CHROMA_DIRの実パスをログ出力（観測性強化）
    from pathlib import Path
    repo_root = Path(__file__).parent.parent.parent
    chroma_path = repo_root / settings.chroma_dir
    logger.info(f"CHROMA_DIR実パス: {chroma_path.absolute()}")
    
    try:
        # /docs/summary と同じタイミングで実行
        build_index()
    except Exception as e:
        # 失敗してもサーバ起動は落とさない（ログだけ出す）
        logger.error(f"起動時のインデックス作成に失敗しました: {type(e).__name__}: {e}")


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {"message": "RAG Quiz App API"}
