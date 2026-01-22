#!/usr/bin/env python3
"""
チャンキングのデバッグスクリプト

PDFから抽出されたテキストがどのようにチャンク化されているか確認します。
"""
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.settings import settings
from app.docs.loader import load_documents
from app.rag.chunking import chunk_document_for_rag

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    print("=" * 60)
    print("チャンキングデバッグ")
    print("=" * 60)
    
    # ドキュメントを読み込む
    documents = load_documents(settings.docs_dir)
    
    # 「強盗」を含むドキュメントを探す
    target_doc = None
    for doc in documents:
        if "強盗" in doc.text:
            target_doc = doc
            break
    
    if target_doc is None:
        print("❌ 「強盗」を含むドキュメントが見つかりません")
        return
    
    print(f"\n[1] 対象ドキュメント")
    print(f"   source: {target_doc.source}")
    print(f"   page: {target_doc.page}")
    print(f"   テキスト長: {len(target_doc.text)}文字")
    
    # 「強盗」の出現箇所を確認
    print(f"\n[2] 「強盗」の出現箇所")
    lines = target_doc.text.split('\n')
    for i, line in enumerate(lines):
        if "強盗" in line:
            print(f"   行{i+1}: {line[:100]}...")
            # 前後5行も表示
            start = max(0, i - 5)
            end = min(len(lines), i + 6)
            print(f"   前後コンテキスト:")
            for j in range(start, end):
                marker = ">>> " if j == i else "    "
                print(f"   {marker}行{j+1}: {lines[j][:80]}")
            print()
    
    # チャンキングを実行
    print(f"\n[3] チャンキング結果")
    chunks = chunk_document_for_rag(
        target_doc,
        chunk_size=settings.section_chunk_size,
        chunk_overlap=settings.section_chunk_overlap,
    )
    
    print(f"   チャンク数: {len(chunks)}")
    
    # 「強盗」を含むチャンクを探す
    robbery_chunks = []
    for chunk in chunks:
        if "強盗" in chunk.text:
            robbery_chunks.append(chunk)
    
    print(f"   「強盗」を含むチャンク数: {len(robbery_chunks)}")
    
    if len(robbery_chunks) == 0:
        print("   ❌ 「強盗」を含むチャンクがありません")
    else:
        print(f"\n[4] 「強盗」を含むチャンク詳細")
        for i, chunk in enumerate(robbery_chunks[:3]):
            print(f"   [{i+1}] chunk_index={chunk.chunk_index}, 長さ={len(chunk.text)}文字")
            print(f"        text={chunk.text[:200]}...")
            print()
    
    # 「万引き」を含むチャンクも確認
    shoplifting_chunks = [c for c in chunks if "万引き" in c.text]
    print(f"\n[5] 「万引き」を含むチャンク数: {len(shoplifting_chunks)}")
    
    if len(shoplifting_chunks) > 0:
        print("   ⚠️ 「万引き」を含むチャンクが存在します")
        for i, chunk in enumerate(shoplifting_chunks[:2]):
            print(f"   [{i+1}] chunk_index={chunk.chunk_index}, 長さ={len(chunk.text)}文字")
            print(f"        text={chunk.text[:200]}...")
            print()
    
    # 「強盗」と「万引き」が混在しているチャンクを確認
    mixed_chunks = [c for c in chunks if "強盗" in c.text and "万引き" in c.text]
    if len(mixed_chunks) > 0:
        print(f"\n[6] ⚠️ 「強盗」と「万引き」が混在するチャンク: {len(mixed_chunks)}件")
        for i, chunk in enumerate(mixed_chunks):
            print(f"   [{i+1}] chunk_index={chunk.chunk_index}")
            print(f"        text={chunk.text[:300]}...")
            print()
    
    print("=" * 60)
    print("デバッグ完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
