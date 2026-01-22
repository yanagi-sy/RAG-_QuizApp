"""
チャンク監査スクリプト

Chroma collectionから全チャンクを取得し、統計とキーワード含有チャンクを出力する。
「強盗」と「万引き」が同一チャンクに混在しているかをチェックする。
"""
import sys
from pathlib import Path
from collections import Counter
from typing import List, Dict

# プロジェクトルートをパスに追加
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore, get_collection_count


def audit_chunking(keywords: List[str] = None, min_chunk_len: int = 80):
    """
    チャンク監査を実行
    
    Args:
        keywords: チェックするキーワードリスト（デフォルト: ["強盗", "万引き"]）
        min_chunk_len: 混在判定から除外する最小チャンク長（デフォルト: 80）
    """
    if keywords is None:
        keywords = ["強盗", "万引き"]
    
    print("=== チャンク監査開始 ===\n")
    
    # ChromaDBコレクションを取得
    collection = get_vectorstore(settings.chroma_dir)
    total_count = get_collection_count(collection)
    
    if total_count == 0:
        print("警告: チャンクが0件です。インデックスを構築してください。")
        return
    
    print(f"総チャンク数: {total_count}\n")
    
    # 全チャンクを取得
    result = collection.get(include=["documents", "metadatas"])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])
    
    if not documents:
        print("警告: ドキュメントが取得できませんでした。")
        return
    
    # source別チャンク数
    source_counts = Counter([m.get("source", "unknown") for m in metadatas])
    print("source別チャンク数:")
    for source, count in sorted(source_counts.items()):
        print(f"  {source}: {count}件")
    print()
    
    # chunk長の統計
    chunk_lengths = [len(doc) for doc in documents]
    chunk_lengths.sort()
    
    if chunk_lengths:
        min_len = chunk_lengths[0]
        max_len = chunk_lengths[-1]
        avg_len = sum(chunk_lengths) / len(chunk_lengths)
        p95_idx = int(len(chunk_lengths) * 0.95)
        p95_len = chunk_lengths[p95_idx] if p95_idx < len(chunk_lengths) else max_len
        
        print("chunk長の統計:")
        print(f"  min: {min_len}文字")
        print(f"  avg: {avg_len:.1f}文字")
        print(f"  p95: {p95_len}文字")
        print(f"  max: {max_len}文字")
        print()
    
    # キーワード含有チャンクの検索
    keyword_chunks: Dict[str, List[Dict]] = {kw: [] for kw in keywords}
    
    for i, (doc, meta) in enumerate(zip(documents, metadatas)):
        for keyword in keywords:
            if keyword in doc:
                keyword_chunks[keyword].append({
                    "index": i,
                    "source": meta.get("source", "unknown"),
                    "page": meta.get("page"),
                    "chunk_index": meta.get("chunk_index", i),
                    "length": len(doc),
                    "head": doc[:50] + "..." if len(doc) > 50 else doc,
                    "tail": "..." + doc[-50:] if len(doc) > 50 else doc,
                    "text": doc
                })
    
    # キーワード含有チャンクの一覧
    for keyword in keywords:
        chunks = keyword_chunks[keyword]
        print(f"「{keyword}」を含むチャンク: {len(chunks)}件")
        
        if chunks:
            print("  詳細:")
            for chunk in chunks[:10]:  # 最大10件表示
                print(f"    - {chunk['source']} (p.{chunk['page']}, idx={chunk['chunk_index']}, len={chunk['length']})")
                print(f"      head: {chunk['head']}")
                print(f"      tail: {chunk['tail']}")
            
            if len(chunks) > 10:
                print(f"    ... 他 {len(chunks) - 10}件")
        print()
    
    # 混在チェック（80文字未満は除外）
    mixed_chunks = []
    for i, (doc, meta) in enumerate(zip(documents, metadatas)):
        if len(doc) < min_chunk_len:
            continue  # 短すぎるチャンクは除外
        
        # 複数のキーワードが含まれているかチェック
        found_keywords = [kw for kw in keywords if kw in doc]
        if len(found_keywords) >= 2:
            mixed_chunks.append({
                "index": i,
                "source": meta.get("source", "unknown"),
                "page": meta.get("page"),
                "chunk_index": meta.get("chunk_index", i),
                "length": len(doc),
                "keywords": found_keywords,
                "preview": doc[:200] + "..." if len(doc) > 200 else doc
            })
    
    print(f"混在チェック結果（{min_chunk_len}文字以上のチャンクのみ）:")
    if mixed_chunks:
        print(f"  ⚠️ 混在チャンク: {len(mixed_chunks)}件")
        print("  詳細:")
        for chunk in mixed_chunks[:5]:  # 最大5件表示
            print(f"    - {chunk['source']} (p.{chunk['page']}, idx={chunk['chunk_index']}, len={chunk['length']})")
            print(f"      含まれるキーワード: {', '.join(chunk['keywords'])}")
            print(f"      プレビュー: {chunk['preview']}")
            print()
        
        if len(mixed_chunks) > 5:
            print(f"    ... 他 {len(mixed_chunks) - 5}件")
    else:
        print(f"  ✅ 混在なし（{keywords} は別チャンクに分離されています）")
    print()
    
    print("=== チャンク監査完了 ===")


if __name__ == "__main__":
    audit_chunking()
