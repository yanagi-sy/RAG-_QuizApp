#!/bin/bash
# Quiz生成品質テスト
# 
# 目的: 全source×全level×count=5で安定してlen==5を達成できるか確認
# 観測: dropped_reasons をログ出力し、改善の観測ができること

set -euo pipefail

API_BASE="http://localhost:8000"
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "Quiz生成品質テスト"
echo "========================================="
echo ""

# 資料一覧を取得
echo "資料一覧を取得中..."
SOURCES_RESPONSE=$(curl -s -X GET "$API_BASE/sources")
SOURCES=$(echo "$SOURCES_RESPONSE" | jq -r '.sources[]' 2>/dev/null || echo "")

if [ -z "$SOURCES" ]; then
    echo -e "${RED}エラー: 資料一覧の取得に失敗しました${NC}"
    echo "レスポンス: $SOURCES_RESPONSE"
    exit 1
fi

echo -e "${GREEN}資料一覧:${NC}"
echo "$SOURCES" | while read -r source; do
    echo "  - $source"
done
echo ""

# テストケース定義（全資料 + 全資料まとめ）
LEVELS=("beginner" "intermediate" "advanced")
LEVEL_LABELS=("初級" "中級" "上級")
COUNT=5

# 結果集計用
declare -A test_results

# テスト実行関数
run_test() {
    local source="$1"
    local source_label="$2"
    local level="$3"
    local level_label="$4"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    # リクエストボディを構築
    if [ -z "$source" ]; then
        REQUEST_BODY="{\"level\":\"$level\",\"count\":$COUNT,\"debug\":true}"
    else
        REQUEST_BODY="{\"level\":\"$level\",\"count\":$COUNT,\"source_ids\":[\"$source\"],\"debug\":true}"
    fi
    
    # API呼び出し
    RESPONSE=$(curl -s -X POST "$API_BASE/quiz/generate" \
        -H "Content-Type: application/json" \
        -d "$REQUEST_BODY")
    
    # レスポンスから情報を抽出
    QUIZZES_COUNT=$(echo "$RESPONSE" | jq -r '.quizzes | length')
    GENERATED_TRUE=$(echo "$RESPONSE" | jq -r '.debug.generated_true_count // 0')
    GENERATED_FALSE=$(echo "$RESPONSE" | jq -r '.debug.generated_false_count // 0')
    DROPPED_REASONS=$(echo "$RESPONSE" | jq -c '.debug.dropped_reasons // {}')
    ACCEPTED_COUNT=$(echo "$RESPONSE" | jq -r '.debug.accepted_count // 0')
    REJECTED_COUNT=$(echo "$RESPONSE" | jq -r '.debug.rejected_count // 0')
    
    # 成功判定: quizzes.length == COUNT
    if [ "$QUIZZES_COUNT" = "$COUNT" ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "${GREEN}✓${NC} ${source_label} × ${level_label}: quizzes=$QUIZZES_COUNT (○=$GENERATED_TRUE, ×=$GENERATED_FALSE)"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "${RED}✗${NC} ${source_label} × ${level_label}: quizzes=$QUIZZES_COUNT/${COUNT} (○=$GENERATED_TRUE, ×=$GENERATED_FALSE)"
        echo "  accepted=$ACCEPTED_COUNT, rejected=$REJECTED_COUNT"
        
        # dropped_reasons を表示
        if [ "$DROPPED_REASONS" != "{}" ]; then
            echo -e "${YELLOW}  Dropped Reasons:${NC}"
            echo "$DROPPED_REASONS" | jq -C '.'
        fi
    fi
}

# メインテスト
echo "========================================="
echo "テスト開始"
echo "========================================="
echo ""

# 1. 全資料まとめ × 3難易度
echo -e "${BLUE}[全資料まとめ]${NC}"
for j in "${!LEVELS[@]}"; do
    level="${LEVELS[$j]}"
    level_label="${LEVEL_LABELS[$j]}"
    
    run_test "" "全資料" "$level" "$level_label"
    sleep 0.3
done
echo ""

# 2. 各資料 × 3難易度
echo "$SOURCES" | while read -r source; do
    if [ -n "$source" ]; then
        echo -e "${BLUE}[$source]${NC}"
        
        for j in "${!LEVELS[@]}"; do
            level="${LEVELS[$j]}"
            level_label="${LEVEL_LABELS[$j]}"
            
            run_test "$source" "$source" "$level" "$level_label"
            sleep 0.3
        done
        echo ""
    fi
done

# 最終結果サマリー
echo "========================================="
echo "最終結果サマリー"
echo "========================================="
echo "総テスト数: $TOTAL_TESTS"
echo -e "${GREEN}成功: $PASSED_TESTS${NC}"
echo -e "${RED}失敗: $FAILED_TESTS${NC}"

if [ $TOTAL_TESTS -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($PASSED_TESTS/$TOTAL_TESTS)*100}")
    echo "成功率: $SUCCESS_RATE%"
fi
echo ""

# 受け入れ条件チェック
if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}受け入れ条件: 合格 ✓${NC}"
    echo -e "${GREEN}全テストで count=$COUNT を達成しました${NC}"
    echo -e "${GREEN}=========================================${NC}"
    exit 0
else
    echo -e "${RED}=========================================${NC}"
    echo -e "${RED}受け入れ条件: 不合格 ✗${NC}"
    echo -e "${RED}失敗が $FAILED_TESTS 件発生しました${NC}"
    echo -e "${RED}dropped_reasons を確認して改善してください${NC}"
    echo -e "${RED}=========================================${NC}"
    exit 1
fi
