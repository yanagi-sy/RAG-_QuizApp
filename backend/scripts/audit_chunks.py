"""
チャンク詳細監査スクリプト

特定キーワードを含むチャンクを詳細に監査し、
前後チャンクとの関係や他キーワードの混在を確認する。
"""
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict

# プロジェクトルートをパスに追加
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.settings import settings
from app.rag.vectorstore import get_vectorstore, get_collection_count


def audit_chunks(
    source: Optional[str] = None,
    keyword: str = "強盗",
    context_n: int = 1,
    output_file: str = "../docs/REPORT_chunk_audit.md"
):
    """
    特定キーワードを含むチャンクを詳細に監査
    
    Args:
        source: 対象source（Noneなら全source）
        keyword: 検索キーワード
        context_n: 前後何件のチャンクを含めるか
        output_file: 出力ファイルパス（repo_root相対）
    """
    print(f"=== チャンク詳細監査開始 ===")
    print(f"  keyword: {keyword}")
    print(f"  source: {source or '全source'}")
    print(f"  context_n: {context_n}\n")
    
    # Vectorstoreからチャンクを取得
    collection = get_vectorstore(settings.chroma_dir)
    total_count = get_collection_count(collection)
    
    print(f"総チャンク数: {total_count}\n")
    
    if total_count == 0:
        print("警告: チャンクが0件です。インデックスを構築してください。")
        return
    
    # 全チャンクを取得
    result = collection.get(
        include=["documents", "metadatas"]
    )
    
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])
    ids = result.get("ids", [])
    
    if not documents:
        print("警告: ドキュメントが取得できませんでした。")
        return
    
    # sourceでフィルタ
    if source:
        filtered_indices = [
            i for i, metadata in enumerate(metadatas)
            if metadata.get("source") == source
        ]
    else:
        filtered_indices = list(range(len(documents)))
    
    print(f"対象チャンク数: {len(filtered_indices)}\n")
    
    # keywordを含むチャンクを検索
    keyword_chunks = []
    for idx in filtered_indices:
        if keyword in documents[idx]:
            keyword_chunks.append({
                "index": idx,
                "chunk_id": ids[idx] if ids else str(idx),
                "source": metadatas[idx].get("source", "unknown"),
                "page": metadatas[idx].get("page"),
                "chunk_index": metadatas[idx].get("chunk_index", idx),
                "text": documents[idx],
                "text_len": len(documents[idx]),
            })
    
    print(f"「{keyword}」を含むチャンク: {len(keyword_chunks)}件\n")
    
    # レポート生成
    output_path = repo_root / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# チャンク監査レポート\n\n")
        f.write(f"## 監査条件\n\n")
        f.write(f"- **キーワード**: {keyword}\n")
        f.write(f"- **対象source**: {source or '全source'}\n")
        f.write(f"- **前後コンテキスト**: {context_n}件\n")
        f.write(f"- **総チャンク数**: {total_count}\n")
        f.write(f"- **対象チャンク数**: {len(filtered_indices)}\n")
        f.write(f"- **ヒット件数**: {len(keyword_chunks)}\n\n")
        
        f.write(f"---\n\n")
        f.write(f"## 詳細結果\n\n")
        
        for i, chunk_info in enumerate(keyword_chunks):
            idx = chunk_info["index"]
            
            f.write(f"### [{i+1}] チャンク詳細\n\n")
            f.write(f"- **chunk_id**: {chunk_info['chunk_id']}\n")
            f.write(f"- **source**: {chunk_info['source']}\n")
            f.write(f"- **page**: {chunk_info['page']}\n")
            f.write(f"- **chunk_index**: {chunk_info['chunk_index']}\n")
            f.write(f"- **text_len**: {chunk_info['text_len']}文字\n\n")
            
            # 該当チャンクの本文プレビュー
            text = chunk_info["text"]
            f.write(f"**チャンク本文（先頭200文字）:**\n")
            f.write(f"```\n{text[:200]}\n```\n\n")
            
            if len(text) > 200:
                f.write(f"**チャンク本文（末尾200文字）:**\n")
                f.write(f"```\n...{text[-200:]}\n```\n\n")
            
            # 他キーワードの混在チェック
            other_keywords = ["万引き", "詐欺", "警察", "110番"]
            found_keywords = [kw for kw in other_keywords if kw in text]
            
            f.write(f"**他キーワードの混在:**\n")
            if found_keywords:
                f.write(f"- ⚠️ 以下のキーワードが同一チャンク内に存在: {', '.join(found_keywords)}\n")
                
                # 各キーワードの周辺を表示
                for kw in found_keywords:
                    pos = text.find(kw)
                    if pos >= 0:
                        start = max(0, pos - 50)
                        end = min(len(text), pos + 50)
                        f.write(f"  - 「{kw}」周辺: `...{text[start:end]}...`\n")
            else:
                f.write(f"- ✅ 他の主要キーワードは含まれていません\n")
            
            f.write(f"\n")
            
            # 前後チャンクの表示
            if context_n > 0:
                f.write(f"**前後チャンク（context_n={context_n}）:**\n\n")
                
                # 前のチャンク
                for offset in range(context_n, 0, -1):
                    prev_idx = idx - offset
                    if 0 <= prev_idx < len(documents):
                        prev_text = documents[prev_idx]
                        prev_meta = metadatas[prev_idx]
                        
                        f.write(f"**[前-{offset}] chunk_index={prev_meta.get('chunk_index', prev_idx)}, len={len(prev_text)}**\n")
                        f.write(f"```\n{prev_text[:150]}...\n```\n")
                        
                        # 他キーワードチェック
                        prev_found = [kw for kw in [keyword] + other_keywords if kw in prev_text]
                        if prev_found:
                            f.write(f"- 含まれるキーワード: {', '.join(prev_found)}\n")
                        f.write(f"\n")
                
                # 後のチャンク
                for offset in range(1, context_n + 1):
                    next_idx = idx + offset
                    if next_idx < len(documents):
                        next_text = documents[next_idx]
                        next_meta = metadatas[next_idx]
                        
                        f.write(f"**[後+{offset}] chunk_index={next_meta.get('chunk_index', next_idx)}, len={len(next_text)}**\n")
                        f.write(f"```\n{next_text[:150]}...\n```\n")
                        
                        # 他キーワードチェック
                        next_found = [kw for kw in [keyword] + other_keywords if kw in next_text]
                        if next_found:
                            f.write(f"- 含まれるキーワード: {', '.join(next_found)}\n")
                        f.write(f"\n")
            
            f.write(f"---\n\n")
        
        # サマリー
        f.write(f"## サマリー\n\n")
        
        mixed_count = sum(
            1 for c in keyword_chunks
            if any(kw in c["text"] for kw in ["万引き", "詐欺"])
        )
        
        f.write(f"- **「{keyword}」を含むチャンク**: {len(keyword_chunks)}件\n")
        f.write(f"- **他キーワード（万引き/詐欺）と混在**: {mixed_count}件\n")
        
        if mixed_count > 0:
            f.write(f"\n⚠️ **結論**: チャンクが粗く、異なるトピックが混在しています。\n")
            f.write(f"   → 見出し境界を尊重するチャンク戦略への変更を推奨します。\n\n")
        else:
            f.write(f"\n✅ **結論**: チャンクは適切に分離されています。\n")
            f.write(f"   → トピックズレは検索スコアリング/リランキングの問題の可能性があります。\n\n")
    
    print(f"\n✅ レポート出力完了: {output_path}")
    print(f"\n内容を確認してください:")
    print(f"  cat {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="チャンク詳細監査")
    parser.add_argument("--source", type=str, default=None, help="対象source")
    parser.add_argument("--keyword", type=str, default="強盗", help="検索キーワード")
    parser.add_argument("--context-n", type=int, default=1, help="前後チャンク数")
    parser.add_argument("--output", type=str, default="../docs/REPORT_chunk_audit.md", help="出力ファイル")
    
    args = parser.parse_args()
    
    audit_chunks(
        source=args.source,
        keyword=args.keyword,
        context_n=args.context_n,
        output_file=args.output
    )
