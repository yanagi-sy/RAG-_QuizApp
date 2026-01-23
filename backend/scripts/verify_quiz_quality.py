"""
クイズ生成品質検証スクリプト

すべてのファイル・難易度でクイズ生成が品質を保って生成できるか検証する。
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.settings import settings
from app.quiz.retrieval import retrieve_for_quiz
from app.quiz.generation_handler import generate_quizzes_with_retry
from app.schemas.quiz import QuizGenerateRequest

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def verify_quiz_generation(
    source_id: str,
    level: str,
    count: int = 5,
    max_attempts: int = 3
) -> Dict:
    """
    クイズ生成を検証する
    
    Args:
        source_id: ソースID
        level: 難易度 (beginner/intermediate/advanced)
        count: 生成数
        max_attempts: 最大試行回数
        
    Returns:
        検証結果の辞書
    """
    logger.info(f"[VERIFY] 開始: source={source_id}, level={level}, count={count}")
    
    # リクエストを作成
    request = QuizGenerateRequest(
        level=level,
        count=count,
        source_ids=[source_id],
        save=False,
        debug=True
    )
    
    # citationsを取得
    citations, debug_info = retrieve_for_quiz(
        source_ids=[source_id],
        level=level,
        count=count,
        debug=True
    )
    
    if len(citations) == 0:
        return {
            "source": source_id,
            "level": level,
            "success": False,
            "error": "citationsが0件",
            "citations_count": 0,
        }
    
    # クイズ生成
    request_id = "verify-test"
    accepted_quizzes, rejected_items, error_info, attempts, attempt_errors, aggregated_stats = await generate_quizzes_with_retry(
        request=request,
        target_count=count,
        citations=citations,
        request_id=request_id,
    )
    
    # 検証項目
    verification_results = {
        "source": source_id,
        "level": level,
        "requested_count": count,
        "generated_count": len(accepted_quizzes),
        "success": len(accepted_quizzes) >= count,
        "citations_count": len(citations),
        "attempts": attempts,
        "rejected_count": len(rejected_items),
        "error_info": error_info,
    }
    
    # 品質チェック
    quality_issues = []
    
    # 1. 生成数チェック
    if len(accepted_quizzes) < count:
        quality_issues.append({
            "type": "count_shortage",
            "message": f"生成数が不足: {len(accepted_quizzes)}/{count}",
        })
    
    # 2. 英語での生成チェック
    english_statements = []
    for quiz in accepted_quizzes:
        statement = quiz.statement
        # 最初の50文字に英字が含まれている場合は英語の可能性が高い
        if any(ord(c) < 128 and c.isalpha() for c in statement[:50]):
            english_statements.append(statement[:50])
    
    if len(english_statements) > 0:
        quality_issues.append({
            "type": "english_generation",
            "message": f"英語での生成が{len(english_statements)}件検出",
            "examples": english_statements[:3],
        })
    
    # 3. 抽象的表現チェック
    abstract_patterns = [
        "異常が検出された場合",
        "特定の条件が満たされた場合",
        "警報が発報した場合",
    ]
    abstract_statements = []
    for quiz in accepted_quizzes:
        statement = quiz.statement
        for pattern in abstract_patterns:
            if pattern in statement:
                abstract_statements.append({
                    "statement": statement[:50],
                    "pattern": pattern,
                })
                break
    
    if len(abstract_statements) > 0:
        quality_issues.append({
            "type": "abstract_expression",
            "message": f"抽象的表現が{len(abstract_statements)}件検出",
            "examples": abstract_statements[:3],
        })
    
    # 4. 出題箇所の重複チェック
    citation_keys = set()
    duplicate_citations = []
    for quiz in accepted_quizzes:
        for citation in quiz.citations:
            citation_key = (
                citation.source,
                citation.page,
                citation.quote[:60] if citation.quote else ""
            )
            if citation_key in citation_keys:
                duplicate_citations.append({
                    "statement": quiz.statement[:50],
                    "citation": f"{citation.source}(p.{citation.page})",
                })
            citation_keys.add(citation_key)
    
    if len(duplicate_citations) > 0:
        quality_issues.append({
            "type": "citation_duplicate",
            "message": f"出題箇所の重複が{len(duplicate_citations)}件検出",
            "examples": duplicate_citations[:3],
        })
    
    # 5. source不一致チェック
    source_mismatches = []
    expected_source = source_id
    for quiz in accepted_quizzes:
        for citation in quiz.citations:
            if citation.source != expected_source:
                source_mismatches.append({
                    "statement": quiz.statement[:50],
                    "expected": expected_source,
                    "actual": citation.source,
                })
    
    if len(source_mismatches) > 0:
        quality_issues.append({
            "type": "source_mismatch",
            "message": f"source不一致が{len(source_mismatches)}件検出",
            "examples": source_mismatches[:3],
        })
    
    # 6. 基本的な文型チェック（いつ・誰が・何を・どうする）
    missing_elements = []
    for quiz in accepted_quizzes:
        statement = quiz.statement
        # 「いつ」のチェック（具体的な状況・条件・タイミングが含まれているか）
        has_when = any(keyword in statement for keyword in ["時", "場合", "前", "後", "中", "開始", "終了"])
        # 「誰が」のチェック（主体が含まれているか）
        has_who = any(keyword in statement for keyword in ["担当者", "スタッフ", "作業員", "者", "員"])
        # 「どうする」のチェック（行為が含まれているか）
        has_action = any(keyword in statement for keyword in ["する", "行う", "確認", "報告", "対応", "実行"])
        
        missing = []
        if not has_when:
            missing.append("いつ")
        if not has_who:
            missing.append("誰が")
        if not has_action:
            missing.append("どうする")
        
        if len(missing) > 0:
            missing_elements.append({
                "statement": statement[:50],
                "missing": missing,
            })
    
    if len(missing_elements) > 0:
        quality_issues.append({
            "type": "missing_basic_structure",
            "message": f"基本的な文型の要素が不足しているクイズが{len(missing_elements)}件",
            "examples": missing_elements[:3],
        })
    
    verification_results["quality_issues"] = quality_issues
    verification_results["quality_issues_count"] = len(quality_issues)
    
    # 統計情報を追加
    verification_results["stats"] = aggregated_stats
    
    logger.info(
        f"[VERIFY] 完了: source={source_id}, level={level}, "
        f"generated={len(accepted_quizzes)}, issues={len(quality_issues)}"
    )
    
    return verification_results


async def main():
    """
    メイン処理：すべてのファイル・難易度で検証を実行
    """
    # 検証対象のファイル
    source_ids = [
        "sample.txt",
        "sample2.txt",
        "sample3.txt",
        "清掃マニュアル（サンプル：小売店）.pdf",
        "防犯・災害対応マニュアル（サンプル）.pdf",
    ]
    
    # 検証対象の難易度
    levels = ["beginner", "intermediate", "advanced"]
    
    # 検証結果を格納
    all_results = []
    
    # すべての組み合わせで検証
    for source_id in source_ids:
        for level in levels:
            try:
                result = await verify_quiz_generation(
                    source_id=source_id,
                    level=level,
                    count=5,
                    max_attempts=3
                )
                all_results.append(result)
            except Exception as e:
                logger.error(f"[VERIFY] エラー: source={source_id}, level={level}, error={e}")
                all_results.append({
                    "source": source_id,
                    "level": level,
                    "success": False,
                    "error": str(e),
                })
    
    # 結果を集計
    total_tests = len(all_results)
    successful_tests = sum(1 for r in all_results if r.get("success", False))
    tests_with_issues = sum(1 for r in all_results if r.get("quality_issues_count", 0) > 0)
    
    # 結果を出力
    print("\n" + "="*80)
    print("クイズ生成品質検証結果")
    print("="*80)
    print(f"総テスト数: {total_tests}")
    print(f"成功数: {successful_tests}")
    print(f"失敗数: {total_tests - successful_tests}")
    print(f"品質問題あり: {tests_with_issues}")
    print("\n詳細結果:")
    
    for result in all_results:
        source = result.get("source", "unknown")
        level = result.get("level", "unknown")
        success = result.get("success", False)
        generated = result.get("generated_count", 0)
        requested = result.get("requested_count", 0)
        issues_count = result.get("quality_issues_count", 0)
        
        status = "✅" if success and issues_count == 0 else "⚠️" if success else "❌"
        print(f"{status} {source} ({level}): {generated}/{requested}問生成, 品質問題: {issues_count}件")
        
        if issues_count > 0:
            for issue in result.get("quality_issues", []):
                print(f"  - {issue['type']}: {issue['message']}")
    
    # JSONファイルに保存
    output_file = project_root / "quiz_quality_verification_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n詳細結果を保存しました: {output_file}")
    
    # サマリー
    print("\n" + "="*80)
    print("サマリー")
    print("="*80)
    
    # レベル別の成功率
    for level in levels:
        level_results = [r for r in all_results if r.get("level") == level]
        level_success = sum(1 for r in level_results if r.get("success", False))
        level_total = len(level_results)
        success_rate = (level_success / level_total * 100) if level_total > 0 else 0
        print(f"{level}: {level_success}/{level_total} ({success_rate:.1f}%)")
    
    # ソース別の成功率
    print("\nソース別:")
    for source_id in source_ids:
        source_results = [r for r in all_results if r.get("source") == source_id]
        source_success = sum(1 for r in source_results if r.get("success", False))
        source_total = len(source_results)
        success_rate = (source_success / source_total * 100) if source_total > 0 else 0
        print(f"{source_id}: {source_success}/{source_total} ({success_rate:.1f}%)")
    
    # 品質問題の内訳
    print("\n品質問題の内訳:")
    issue_types = {}
    for result in all_results:
        for issue in result.get("quality_issues", []):
            issue_type = issue.get("type", "unknown")
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    
    for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {issue_type}: {count}件")


if __name__ == "__main__":
    asyncio.run(main())
