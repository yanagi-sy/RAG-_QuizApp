"""
Quiz retrieval ロジックのテストスクリプト
"""
import logging
import sys
from pathlib import Path

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# app モジュールをインポート可能にする
sys.path.insert(0, str(Path(__file__).parent))

from app.quiz.retrieval import retrieve_for_quiz

def test_retrieval():
    """retrieval をテスト"""
    print("\n=== Quiz Retrieval Test ===\n")
    
    # sample2.txt で beginner レベル、count=3
    print("Test 1: sample2.txt, beginner, count=3")
    citations, debug_info = retrieve_for_quiz(
        source_ids=["sample2.txt"],
        level="beginner",
        count=3,
        debug=True
    )
    
    print(f"\nCitations: {len(citations)} 件")
    print(f"Debug info:")
    if debug_info:
        for key, value in debug_info.items():
            print(f"  {key}: {value}")
    
    # 全資料で intermediate レベル、count=5
    print("\n\nTest 2: all sources, intermediate, count=5")
    citations, debug_info = retrieve_for_quiz(
        source_ids=None,
        level="intermediate",
        count=5,
        debug=True
    )
    
    print(f"\nCitations: {len(citations)} 件")
    print(f"Debug info:")
    if debug_info:
        for key, value in debug_info.items():
            print(f"  {key}: {value}")

if __name__ == "__main__":
    test_retrieval()
