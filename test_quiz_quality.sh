#!/bin/bash
# クイズ生成の品質担保テスト
# 単一ソース指定で count=5 を3回実行し、全quizで citations>=1 と「ください」等が0であることを確認

set -e

API_URL="http://localhost:8000/quiz/generate"

# 利用可能なsource_idを取得（chunk_poolから推測、または手動指定）
# 実際のsource_idは環境に依存するため、ここでは例として使用
SOURCE_ID="${1:-sample.txt}"  # デフォルトは sample.txt

echo "=========================================="
echo "クイズ生成品質担保テスト"
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
            \"debug\": true
        }")
    
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
    
    if [ "$QUIZ_COUNT" -eq 0 ]; then
        echo "⚠️  警告: クイズが0件生成されました"
        continue
    fi
    
    # 各クイズをチェック
    QUIZ_INDEX=0
    CITATIONS_ERROR=0
    FORBIDDEN_PHRASE_ERROR=0
    
    while IFS= read -r quiz; do
        QUIZ_INDEX=$((QUIZ_INDEX + 1))
        STATEMENT=$(echo "$quiz" | jq -r '.statement')
        CITATIONS_COUNT=$(echo "$quiz" | jq '.citations | length')
        CITATIONS_SOURCES=$(echo "$quiz" | jq -r '.citations[].source' | sort -u)
        
        echo ""
        echo "  クイズ $QUIZ_INDEX:"
        echo "    statement: ${STATEMENT:0:60}..."
        echo "    citations数: $CITATIONS_COUNT"
        echo "    citations sources: $(echo $CITATIONS_SOURCES | tr '\n' ' ')"
        
        # citations >= 1 チェック
        if [ "$CITATIONS_COUNT" -lt 1 ]; then
            echo "    ❌ citationsが1件未満です（$CITATIONS_COUNT件）"
            CITATIONS_ERROR=$((CITATIONS_ERROR + 1))
        else
            echo "    ✅ citations数: OK"
        fi
        
        # 禁止表現チェック
        FORBIDDEN_PHRASES=("ください" "お願いします" "しないでください" "してください" "しましょう" "？" "?")
        FOUND_FORBIDDEN=0
        
        for phrase in "${FORBIDDEN_PHRASES[@]}"; do
            if echo "$STATEMENT" | grep -q "$phrase"; then
                echo "    ❌ 禁止表現が含まれています: \"$phrase\""
                FOUND_FORBIDDEN=1
                break
            fi
        done
        
        if [ "$FOUND_FORBIDDEN" -eq 0 ]; then
            echo "    ✅ 禁止表現: OK"
        else
            FORBIDDEN_PHRASE_ERROR=$((FORBIDDEN_PHRASE_ERROR + 1))
        fi
        
        # 「。」で終わるチェック
        if ! echo "$STATEMENT" | grep -q "。$"; then
            echo "    ❌ statementが「。」で終わっていません"
        else
            echo "    ✅ 「。」で終わる: OK"
        fi
        
        # 単一ソースチェック（citationsのsourceが全て同じか）
        UNIQUE_SOURCES_COUNT=$(echo "$CITATIONS_SOURCES" | wc -l | tr -d ' ')
        if [ "$UNIQUE_SOURCES_COUNT" -gt 1 ]; then
            echo "    ⚠️  警告: citationsに複数のsourceが含まれています（$UNIQUE_SOURCES_COUNT件）"
        else
            echo "    ✅ 単一ソース: OK"
        fi
        
    done <<< "$QUIZZES"
    
    echo ""
    echo "  実行 $i/3 の結果:"
    echo "    citations不足: $CITATIONS_ERROR件"
    echo "    禁止表現含む: $FORBIDDEN_PHRASE_ERROR件"
    
    if [ "$CITATIONS_ERROR" -gt 0 ] || [ "$FORBIDDEN_PHRASE_ERROR" -gt 0 ]; then
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
