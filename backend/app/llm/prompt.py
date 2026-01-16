"""
プロンプト生成ロジック
"""
from typing import List

from app.schemas.common import Citation


def build_messages(question: str, citations: List[Citation]) -> List[dict[str, str]]:
    """
    質問と引用からLLM用のメッセージリストを構築
    
    - system方針：根拠に基づく、根拠がなければ分からない
    - citationsを短く整形してcontextに含める
    
    Args:
        question: 質問文
        citations: 引用リスト（最大5件）
        
    Returns:
        LLM用メッセージリスト（[{"role": "system", "content": "..."}, ...]）
    """
    # systemプロンプト：根拠に基づく回答を指示
    system_content = """あなたは与えられた根拠（citations）を基に質問に答えるアシスタントです。

原則：
- 提供された根拠のみを基に回答してください
- 根拠に含まれていない情報は推測せず、「根拠からは分かりません」と述べてください
- 根拠が複数ある場合は、それらを統合して回答してください
- 回答は日本語で、簡潔にまとめてください
- 回答本文には「根拠1」「(根拠2)」「参照3」などの番号参照を書かないでください（根拠はcitationsとして別に表示されるため、本文は結論と理由を自然な日本語で述べてください）"""  # CHANGED: 番号参照排除の指示を追加
    
    # citationsを整形してcontextを作成
    if len(citations) == 0:
        context_parts = ["【根拠】\n根拠が見つかりませんでした。"]
    else:
        context_parts = ["【根拠】"]
        for i, citation in enumerate(citations, 1):
            # sourceとpageの情報
            source_info = citation.source
            if citation.page is not None:
                source_info = f"{citation.source} (p.{citation.page})"
            
            # quoteをそのまま使用（既に240文字程度に整形済み）
            context_parts.append(f"{i}. [{source_info}]\n{citation.quote}")
    
    context_text = "\n\n".join(context_parts)
    
    # userプロンプト：質問と根拠を提示
    user_content = f"""以下の質問に、提供された根拠を基に回答してください。

【質問】
{question}

{context_text}"""
    
    # メッセージリストを構築
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    return messages
