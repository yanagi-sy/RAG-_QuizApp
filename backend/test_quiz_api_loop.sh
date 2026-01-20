#!/bin/bash
# Quiz API の連続テスト（安定性確認）

echo "=== Quiz API 連続テスト（10回） ==="
echo "目標: len=3 が 10回連続で成功すること"
echo ""

SUCCESS=0
FAILED=0

for i in {1..10}; do
  echo -n "Test $i: "
  
  # API 呼び出し（timeout 45秒）
  response=$(curl -s --max-time 45 -X POST http://localhost:8000/quiz/generate \
    -H "Content-Type: application/json" \
    -d '{"level":"beginner","count":3,"source_ids":["sample.txt"],"debug":true}' 2>/dev/null)
  
  # len を抽出
  len=$(echo "$response" | jq -r '.quizzes | length' 2>/dev/null)
  
  if [ "$len" = "3" ]; then
    echo "✓ len=$len"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "✗ len=$len (expected 3)"
    FAILED=$((FAILED + 1))
    
    # エラー情報を表示
    parse_error=$(echo "$response" | jq -r '.debug.parse_error // "none"' 2>/dev/null)
    echo "  parse_error: $parse_error"
  fi
  
  # 1秒待機（サーバー負荷軽減）
  sleep 1
done

echo ""
echo "=== 結果 ==="
echo "成功: $SUCCESS / 10"
echo "失敗: $FAILED / 10"

if [ "$SUCCESS" = "10" ]; then
  echo "✓ 全て成功！"
  exit 0
else
  echo "✗ 一部失敗"
  exit 1
fi
