"""
/ask エンドポイントの引用品質回帰テスト

特定の質問に対して、適切な引用が返されることを自動検証する。
"""
import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

from app.routers.ask import ask_question
from app.schemas.ask import AskRequest


async def test_robbery_citations():
    """
    強盗の質問に対して、適切な引用が返されることをテスト
    
    期待:
    - citations が最低1件以上返される
    - 上位の citation に「強盗」または強盗関連語が含まれる
    - 「万引き」のみの citation が優先されない
    """
    print("=== /ask 回帰テスト: 強盗の質問 ===\n")
    
    # テストケース
    question = "強盗への対応方法を教えてください"
    print(f"質問: {question}\n")
    
    # リクエスト作成
    request = AskRequest(question=question)
    
    # API呼び出し
    try:
        response = await ask_question(request)
    except Exception as e:
        print(f"❌ API呼び出しエラー: {e}")
        return False
    
    # 結果検証
    print(f"回答: {response.answer[:200]}...\n")
    print(f"引用数: {len(response.citations)}\n")
    
    if len(response.citations) == 0:
        print("❌ 失敗: 引用が0件です")
        return False
    
    # 各引用を検証
    print("引用詳細:")
    robbery_related = ["強盗", "凶器", "110番", "警察", "現場保存"]
    
    has_robbery_citation = False
    top_has_shoplifting_only = False
    
    for i, citation in enumerate(response.citations):
        print(f"\n[{i+1}] source: {citation.source}, page: {citation.page}")
        print(f"    quote: {citation.quote[:100]}...")
        
        # 強盗関連語が含まれるか
        contains_robbery = any(keyword in citation.quote for keyword in robbery_related)
        contains_shoplifting = "万引き" in citation.quote
        
        if contains_robbery:
            print(f"    ✅ 強盗関連語を含む")
            has_robbery_citation = True
        
        if contains_shoplifting:
            print(f"    ⚠️  万引きを含む")
            if i == 0:  # 最上位の引用
                if not contains_robbery:
                    top_has_shoplifting_only = True
                    print(f"    ❌ 最上位が万引きのみ（強盗関連語を含まない）")
    
    print("\n--- 検証結果 ---")
    
    # 結果判定
    success = True
    
    if not has_robbery_citation:
        print("❌ 失敗: 強盗関連の引用が1件もありません")
        success = False
    else:
        print("✅ 成功: 強盗関連の引用が含まれています")
    
    if top_has_shoplifting_only:
        print("❌ 失敗: 最上位の引用が万引きのみ（強盗関連語なし）")
        success = False
    else:
        print("✅ 成功: 最上位の引用は適切です")
    
    return success


async def test_disaster_prevention_citations():
    """
    防災の質問に対して、適切な引用が返されることをテスト（回帰確認用）
    """
    print("\n\n=== /ask 回帰テスト: 防災の質問 ===\n")
    
    question = "防災対策で重要なことは？"
    print(f"質問: {question}\n")
    
    request = AskRequest(question=question)
    
    try:
        response = await ask_question(request)
    except Exception as e:
        print(f"❌ API呼び出しエラー: {e}")
        return False
    
    print(f"回答: {response.answer[:200]}...\n")
    print(f"引用数: {len(response.citations)}\n")
    
    if len(response.citations) == 0:
        print("❌ 失敗: 引用が0件です")
        return False
    
    print("✅ 成功: 引用が返されました")
    
    # 簡易検証: 答えと引用が返されればOK
    return True


async def main():
    """
    全テストを実行
    """
    print("=" * 60)
    print(" /ask エンドポイント 回帰テスト")
    print("=" * 60)
    print()
    
    results = []
    
    # テスト1: 強盗の質問
    result1 = await test_robbery_citations()
    results.append(("強盗の質問", result1))
    
    # テスト2: 防災の質問（回帰確認）
    result2 = await test_disaster_prevention_citations()
    results.append(("防災の質問", result2))
    
    # サマリー
    print("\n\n" + "=" * 60)
    print(" テスト結果サマリー")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    # 全体結果
    all_passed = all(result for _, result in results)
    
    print()
    if all_passed:
        print("🎉 全テストが成功しました！")
        return 0
    else:
        print("⚠️  一部のテストが失敗しました。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
