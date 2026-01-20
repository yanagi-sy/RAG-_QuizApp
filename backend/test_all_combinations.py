"""
全資料 / 全難易度でのテスト
"""
import logging
import sys
from pathlib import Path

# ロガー設定
logging.basicConfig(
    level=logging.WARNING,  # WARNING 以上のみ表示
    format='%(levelname)s - %(message)s'
)

# app モジュールをインポート可能にする
sys.path.insert(0, str(Path(__file__).parent))

from app.quiz.retrieval import retrieve_for_quiz

# テスト対象の資料
SOURCES = [
    "sample.txt",
    "sample2.txt",
    "sample3.txt",
    "防犯・安全ナレッジベース.pdf",
    "店舗運営ナレッジベース.pdf"
]

# テスト対象の難易度
LEVELS = ["beginner", "intermediate", "advanced"]

def test_all_combinations():
    """全資料 / 全難易度でテスト"""
    print("\n=== Quiz Retrieval: 全資料 / 全難易度テスト ===\n")
    print("目標: 全ての組み合わせで citations >= 3 件\n")
    
    all_passed = True
    results = []
    
    for source in SOURCES:
        for level in LEVELS:
            citations, debug_info = retrieve_for_quiz(
                source_ids=[source],
                level=level,
                count=5,
                debug=True
            )
            
            passed = len(citations) >= 3
            status = "✓" if passed else "✗"
            
            result = {
                "source": source,
                "level": level,
                "citations": len(citations),
                "passed": passed,
                "status": status
            }
            results.append(result)
            
            if not passed:
                all_passed = False
            
            print(f"{status} {source:40s} / {level:12s} → {len(citations)} citations")
    
    print(f"\n{'='*80}")
    print(f"結果: {'全て合格 ✓' if all_passed else '一部失敗 ✗'}")
    print(f"合格数: {sum(1 for r in results if r['passed'])} / {len(results)}")
    
    # 失敗したケースを表示
    failed = [r for r in results if not r['passed']]
    if failed:
        print(f"\n失敗したケース:")
        for r in failed:
            print(f"  - {r['source']} / {r['level']} → {r['citations']} citations")

if __name__ == "__main__":
    test_all_combinations()
