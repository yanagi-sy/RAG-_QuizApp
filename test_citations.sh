#!/bin/bash
# citations付与のテストスクリプト

echo "=== Citations付与テスト（5問生成×3回） ==="
echo ""

for i in {1..3}; do
  echo "=== Test Run $i ==="
  response=$(curl -s -X POST http://localhost:8000/quiz/generate \
    -H "Content-Type: application/json" \
    -d '{
      "level": "beginner",
      "count": 5,
      "source_ids": null,
      "save": false,
      "debug": true
    }')
  
  # クイズ数とcitationsの確認
  quiz_count=$(echo "$response" | jq '.quizzes | length')
  echo "生成されたクイズ数: $quiz_count"
  
  # 各クイズのcitations確認
  echo "$response" | jq -r '.quizzes[] | 
    "  Quiz \(.id): citations_count=\(.citations | length), source=\(.citations[0].source // "NONE"), page=\(.citations[0].page // "NONE")"'
  
  # citations_count >= 1 の確認
  all_valid=$(echo "$response" | jq '[.quizzes[] | .citations | length >= 1] | all')
  if [ "$all_valid" = "true" ]; then
    echo "  ✅ すべてのクイズでcitations_count >= 1"
  else
    echo "  ❌ citations_count < 1 のクイズが存在します"
  fi
  
  echo ""
done

echo "=== テスト完了 ==="
