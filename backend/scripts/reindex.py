"""
再インデックススクリプト

backend/.chroma を削除してから、全マニュアルを再インデックスする。
"""
import sys
import shutil
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.settings import settings
from app.rag.indexer import build_index
from app.docs.loader import _find_repo_root

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def reindex():
    """
    再インデックスを実行
    
    1. backend/.chroma を削除
    2. build_index(force_rebuild=True) を呼び出し
    """
    logger.info("=== 再インデックス開始 ===\n")
    
    # ChromaDBディレクトリのパスを取得
    repo_root = _find_repo_root()
    chroma_path = (repo_root / settings.chroma_dir).resolve()
    
    # ChromaDBディレクトリを削除
    if chroma_path.exists():
        logger.info(f"削除: {chroma_path}")
        shutil.rmtree(chroma_path)
        logger.info("ChromaDBディレクトリを削除しました\n")
    else:
        logger.info(f"ChromaDBディレクトリが存在しません（スキップ）: {chroma_path}\n")
    
    # 再構築開始
    logger.info("再構築開始...")
    try:
        build_index(force_rebuild=True)
        logger.info("\n✅ 再インデックス完了")
    except Exception as e:
        logger.error(f"\n❌ 再インデックス失敗: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    reindex()
