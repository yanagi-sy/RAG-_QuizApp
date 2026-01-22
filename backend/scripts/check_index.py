#!/usr/bin/env python3
"""
インデックスと検索機能の診断スクリプト

ChromaDBの状態、chunk pool、検索機能を確認します。
"""
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore, get_collection_count
from app.quiz.chunk_pool import get_pool

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    print("=" * 60)
    print("インデックス診断")
    print("=" * 60)
    
    # 1. ChromaDBの状態確認
    print("\n[1] ChromaDBの状態")
    collection = get_vectorstore(settings.chroma_dir)
    count = get_collection_count(collection)
    print(f"  チャンク数: {count}")
    
    if count == 0:
        print("  ❌ インデックスが空です。build_index.pyを実行してください。")
        return
    
    # 2. サンプルチャンクの確認
    print("\n[2] サンプルチャンク（最初の3件）")
    try:
        samples = collection.get(limit=3, include=["documents", "metadatas"])
        ids = samples.get("ids", [])
        documents = samples.get("documents", [])
        metadatas = samples.get("metadatas", [])
        
        for i, (chunk_id, doc, meta) in enumerate(zip(ids, documents, metadatas)):
            source = meta.get("source", "unknown")
            page = meta.get("page", 0)
            text_preview = doc[:100] if doc else ""
            print(f"  [{i+1}] ID={chunk_id}")
            print(f"      source={source}, page={page}")
            print(f"      text={text_preview}...")
    except Exception as e:
        print(f"  ❌ エラー: {type(e).__name__}: {e}")
    
    # 3. source別のチャンク数確認
    print("\n[3] source別のチャンク数")
    try:
        all_data = collection.get(limit=count, include=["metadatas"])
        metadatas = all_data.get("metadatas", [])
        
        from collections import Counter
        sources = [m.get("source", "unknown") for m in metadatas]
        source_counts = Counter(sources)
        
        for source, count in sorted(source_counts.items()):
            print(f"  {source}: {count}件")
    except Exception as e:
        print(f"  ❌ エラー: {type(e).__name__}: {e}")
    
    # 4. chunk poolの状態確認
    print("\n[4] chunk poolの状態")
    try:
        pool = get_pool(collection)
        print(f"  pool内のsource数: {len(pool)}")
        
        if len(pool) == 0:
            print("  ❌ chunk poolが空です。")
        else:
            total_ids = sum(len(ids) for ids in pool.values())
            print(f"  pool内の総ID数: {total_ids}")
            
            for source, ids in sorted(pool.items()):
                print(f"    {source}: {len(ids)}件")
    except Exception as e:
        print(f"  ❌ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. retrieve_for_quizのテスト（サンプリング方式）
    print("\n[5] Quiz用retrievalテスト（サンプリング方式）")
    try:
        from app.quiz.retrieval import retrieve_for_quiz
        
        citations, debug_info = retrieve_for_quiz(
            source_ids=None,  # 全資料対象
            level="beginner",
            count=3,
            debug=True
        )
        
        print(f"  取得されたcitations数: {len(citations)}")
        
        if len(citations) == 0:
            print("  ❌ citationsが0件です")
            if debug_info:
                print(f"  debug情報: {debug_info}")
        else:
            print(f"  ✅ citations取得成功")
            for i, cit in enumerate(citations[:3]):
                print(f"    [{i+1}] source={cit.source}, page={cit.page}")
                print(f"        quote={cit.quote[:80]}...")
        
        if debug_info:
            print(f"\n  debug情報:")
            for key, value in debug_info.items():
                print(f"    {key}: {value}")
    except Exception as e:
        print(f"  ❌ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("診断完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
