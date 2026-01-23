#!/bin/bash
# クイズ生成の品質担保テスト（禁止語チェック）
# 防犯・災害対応マニュアルで count=5 を3回実行し、
# 「店外での身体接触を行う」が○にならないこと、5問揃わない場合はエラーになることを確認

set -e

API_URL="http://localhost:8000/quiz/generate"

# 防犯・災害対応マニュアルのsource_id（実際の環境に合わせて調整）
SOURCE_ID="${1:-防犯・災害対応マニュアル（サンプル）.pdf}"

echo "=========================================="
echo "クイズ生成品質担保テスト（禁止語チェック）"
echo "=========================================="
echo "API URL: $API_URL"
echo "SOURCE ID: $SOURCE_ID"
echo ""

# 3回実行
for i in 1 2 3; do
    echo "----------------------------------------"
    echo "実行 $i/3"
    echo "----------------------------------------"
    
    # クイズ生成リクエスト
    RESPONSE=$(curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"level\": \"beginner\",
            \"count\": 5,
            \"source_ids\": [\"$SOURCE_ID\"],
            \"debug\": true,
            \"save\": false
        }")
    
    # HTTPステータスコードを確認
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"level\": \"beginner\",
            \"count\": 5,
            \"source_ids\": [\"$SOURCE_ID\"],
            \"debug\": true,
            \"save\": false
        }")
    
    echo "HTTP Status Code: $HTTP_CODE"
    
    # 422エラーの場合は正常（規定数に達していない）
    if [ "$HTTP_CODE" -eq 422 ]; then
        echo "✅ 422エラー（規定数未達）が返されました（期待通り）"
        SHORTAGE=$(echo "$RESPONSE" | jq -r '.detail.shortage // .detail.shortage_count // "N/A"')
        echo "   不足数: $SHORTAGE"
        REJECT_COUNTS=$(echo "$RESPONSE" | jq -r '.detail.reject_reason_counts // {}')
        echo "   reject理由内訳: $REJECT_COUNTS"
        continue
    fi
    
    # エラーチェック
    if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
        echo "❌ エラーが発生しました:"
        echo "$RESPONSE" | jq '.error'
        exit 1
    fi
    
    # quizzesを取得
    QUIZZES=$(echo "$RESPONSE" | jq -c '.quizzes[]')
    QUIZ_COUNT=$(echo "$RESPONSE" | jq '.quizzes | length')
    
    echo "生成されたクイズ数: $QUIZ_COUNT"
    
    # 規定数チェック
    if [ "$QUIZ_COUNT" -lt 5 ]; then
        echo "❌ エラー: クイズが規定数（5問）に達していません（$QUIZ_COUNT問）"
        echo "   422エラーが返されるべきです"
        exit 1
    fi
    
    if [ "$QUIZ_COUNT" -eq 0 ]; then
        echo "⚠️  警告: クイズが0件生成されました"
        continue
    fi
    
    # 各クイズをチェック
    QUIZ_INDEX=0
    FORBIDDEN_ERROR=0
    
    while IFS= read -r quiz; do
        QUIZ_INDEX=$((QUIZ_INDEX + 1))
        STATEMENT=$(echo "$quiz" | jq -r '.statement')
        ANSWER_BOOL=$(echo "$quiz" | jq -r '.answer_bool')
        CITATIONS=$(echo "$quiz" | jq -c '.citations[]')
        
        echo ""
        echo "  クイズ $QUIZ_INDEX:"
        echo "    statement: ${STATEMENT:0:80}..."
        echo "    answer_bool: $ANSWER_BOOL"
        
        # 「店外での身体接触を行う」が○になっていないかチェック
        if echo "$STATEMENT" | grep -q "店外での身体接触を行う" && [ "$ANSWER_BOOL" = "true" ]; then
            echo "    ❌ 禁止語チェック失敗: 「店外での身体接触を行う」が○になっています"
            FORBIDDEN_ERROR=$((FORBIDDEN_ERROR + 1))
        else
            echo "    ✅ 禁止語チェック: OK"
        fi
        
        # citationsをチェック
        CITATION_COUNT=0
        while IFS= read -r citation; do
            CITATION_COUNT=$((CITATION_COUNT + 1))
            QUOTE=$(echo "$citation" | jq -r '.quote')
            
            # quoteに禁止語が含まれている場合、statementが肯定形で○ならエラー
            if echo "$QUOTE" | grep -qE "(やってはいけない|禁止|厳禁|してはならない)" && [ "$ANSWER_BOOL" = "true" ]; then
                if echo "$STATEMENT" | grep -qE "(する|行う)" && ! echo "$STATEMENT" | grep -qE "(しない|行わない|禁止|厳禁)"; then
                    echo "    ❌ 禁止語チェック失敗: quoteに禁止語があるのに、statementが肯定形で○になっています"
                    echo "      quote: ${QUOTE:0:60}..."
                    FORBIDDEN_ERROR=$((FORBIDDEN_ERROR + 1))
                fi
            fi
        done <<< "$CITATIONS"
        
        echo "    citations数: $CITATION_COUNT"
        
    done <<< "$QUIZZES"
    
    echo ""
    echo "  実行 $i/3 の結果:"
    echo "    禁止語チェック失敗: $FORBIDDEN_ERROR件"
    
    if [ "$FORBIDDEN_ERROR" -gt 0 ]; then
        echo "    ❌ 品質チェック失敗"
        exit 1
    else
        echo "    ✅ 品質チェック成功"
    fi
done

echo ""
echo "=========================================="
echo "全テスト完了: ✅ 成功"
echo "=========================================="
