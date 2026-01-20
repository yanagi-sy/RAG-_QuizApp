#!/bin/bash
# Quiz API のテスト（全資料 / 全難易度）

echo "=== Quiz API Test: 全資料 / 全難易度 ==="
echo ""

SOURCES=("sample.txt" "sample2.txt" "sample3.txt" "防犯・安全ナレッジベース.pdf" "店舗運営ナレッジベース.pdf")
LEVELS=("beginner" "intermediate" "advanced")

for src in "${SOURCES[@]}"; do
  for lv in "${LEVELS[@]}"; do
    echo "=== $src / $lv ==="
    
    # API 呼び出し（timeout 付き、エラーは無視）
    response=$(curl -s --max-time 30 -X POST http://localhost:8000/quiz/generate \
      -H "Content-Type: application/json" \
      -d "{\"level\":\"$lv\",\"count\":5,\"source_ids\":[\"$src\"],\"debug\":true}" 2>/dev/null)
    
    # debug 情報を抽出（jq でエラーが出ても無視）
    pool_size=$(echo "$response" | jq -r '.debug.quiz_pool_size // "N/A"' 2>/dev/null)
    sample_n=$(echo "$response" | jq -r '.debug.quiz_sample_n // "N/A"' 2>/dev/null)
    selected_n=$(echo "$response" | jq -r '.debug.quiz_selected_n // "N/A"' 2>/dev/null)
    citations=$(echo "$response" | jq -r '.debug.quiz_final_citations_count // "N/A"' 2>/dev/null)
    quizzes_len=$(echo "$response" | jq -r '.quizzes | length // 0' 2>/dev/null)
    
    echo "  Pool: $pool_size, Sample: $sample_n, Selected: $selected_n, Citations: $citations, Quizzes: $quizzes_len"
    echo ""
  done
done
