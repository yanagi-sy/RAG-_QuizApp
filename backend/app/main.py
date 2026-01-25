"""
FastAPIアプリケーションのエントリーポイント（アプリの起動入口）

【初心者向け】
このファイルはRAG Quiz AppのバックエンドAPIサーバーを起動する「玄関」です。
- FastAPI: PythonのWebフレームワーク。REST APIを簡単に作れる
- 起動時に /health, /ask, /quiz などのルート（APIの窓口）を登録し、
  起動イベントでドキュメントをChromaDBにインデックス化します

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

# CORS設定: フロントエンド（Next.js）からAPIを呼ぶ際の跨域通信を許可
# 環境変数 CORS_ORIGINS で許可するオリジン（例: http://localhost:3000）を指定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録: 各APIの「窓口」をURLパスに割り当て
# /health=死活確認, /ask=QA質問, /quiz=クイズ, /judge=採点, /docs=資料, /search=検索
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(ask.router, prefix="/ask", tags=["ask"])
app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])
app.include_router(judge.router, prefix="/judge", tags=["judge"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])
app.include_router(search.router, prefix="/search", tags=["search"])


@app.on_event("startup")
async def startup_event():
    """
    起動時の処理: manuals内のドキュメントをChromaDBに登録（インデックス作成）
    インデックス = 検索用の索引。これがないとQA/Quizで資料を検索できない
    """
    # CHANGED: CHROMA_DIRとDOCS_DIRの実パスをログ出力（観測性強化）
    from pathlib import Path
    from app.docs.loader import _find_repo_root
    
    # CHANGED: repo_rootは_find_repo_root()を使って統一
    repo_root = _find_repo_root()
    chroma_path = (repo_root / settings.chroma_dir).resolve()
    docs_path = (repo_root / settings.docs_dir).resolve()
    
    logger.info(f"CHROMA_DIR実パス: {chroma_path} (exists={chroma_path.exists()})")
    logger.info(f"DOCS_DIR実パス: {docs_path} (exists={docs_path.exists()})")
    
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
