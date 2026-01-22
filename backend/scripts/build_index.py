#!/usr/bin/env python3
"""
RAGインデックス構築スクリプト

manualsディレクトリのドキュメントをChromaDBにインデックス化します。
サーバー起動時にも自動的に実行されますが、手動で再構築したい場合に使用します。

使用方法:
    cd backend
    source .venv/bin/activate
    python scripts/build_index.py [--force]
    
オプション:
    --force: 既存のインデックスを削除して強制的に再構築する
"""
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.indexer import build_index

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='RAGインデックス構築スクリプト')
    parser.add_argument(
        '--force',
        action='store_true',
        help='既存のインデックスを削除して強制的に再構築する'
    )
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("RAGインデックス構築を開始します")
    logger.info(f"force_rebuild: {args.force}")
    logger.info("=" * 60)
    
    try:
        build_index(force_rebuild=args.force)
        logger.info("=" * 60)
        logger.info("RAGインデックス構築が完了しました")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"インデックス構築に失敗しました: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
