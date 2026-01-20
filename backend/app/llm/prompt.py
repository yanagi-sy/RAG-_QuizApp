"""
プロンプト生成ロジック
"""
from typing import List, Literal

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


def build_quiz_generation_messages(
    level: Literal["beginner", "intermediate", "advanced"],
    count: int,
    topic: str | None,
    citations: List[Citation],
) -> tuple[List[dict[str, str]], dict]:
    """
    Quiz生成用のメッセージリストを構築
    
    - 引用（citations）のみを材料にクイズを生成
    - JSON形式で出力（厳守）
    - 引用外の推測は禁止
    - levelに応じた難易度調整
    
    Args:
        level: 難易度（beginner/intermediate/advanced）
        count: 生成するクイズの数
        topic: トピック（オプション）
        citations: 引用リスト
        
    Returns:
        (LLM用メッセージリスト, プロンプト統計情報)
    """
    # systemプロンプト：シンプル版、テンプレート準拠
    system_content = """業務マニュアルから正しい断言文だけを作成します。

出力ルール:
- JSONのみ出力（説明文・コードフェンス・コメント禁止）
- { "quizzes": [...] } の形式のみ
- quizzes配列は指定個数を必ず含める

各quizの必須要素:
- type: "true_false"
- statement: 下記テンプレートのいずれかに従う断言文
- answer_bool: true（常にtrue）
- explanation: 1文のみ、最大80文字（引用の要約、新情報追加禁止）
- citations: 入力で渡された引用をそのまま使用

statementテンプレート:
T3: 「【対象】では【行為】をしてはならない。」
T4: 「【対象】では【行為】を必ず行う。」
T6: 「【条件】の場合、【行為】を行い、その後【確認】を行う。」
T7: 「【操作】の前に【前提条件】を確認しなければならない。」
T10: 「【リスク条件】がある場合、【行為】をしてはならない。」
T11: 「【判断条件】に該当する場合、【対応】を行わなければならない。」

禁止表現:
疑問形（?）、曖昧表現（場合がある、望ましい、基本的に、状況による、適宜）

テンプレートの【】部分は引用から抽出。引用に無い情報は追加しない。

"""

    # citationsを制限・整形（厳格なタイムアウト対策）
    from app.core.settings import settings
    
    # LLMへ渡すcitations数を制限
    max_citations = settings.quiz_context_top_n
    max_quote_len = settings.quiz_quote_max_len
    max_total_chars = settings.quiz_total_quote_max_chars
    
    # citations数を制限し、total_quote_charsが上限を超えないように調整
    citations_for_llm = []
    total_quote_chars = 0
    
    for citation in citations[:max_citations]:
        # quoteをトリム
        trimmed_quote = citation.quote[:max_quote_len] if len(citation.quote) > max_quote_len else citation.quote
        
        # 総文字数チェック
        if total_quote_chars + len(trimmed_quote) > max_total_chars:
            # 上限を超える場合は、残り分だけ追加して終了
            remaining = max_total_chars - total_quote_chars
            if remaining > 50:  # 最低50文字ないと意味がないので追加しない
                trimmed_quote = trimmed_quote[:remaining]
                citations_for_llm.append((citation, trimmed_quote))
                total_quote_chars += len(trimmed_quote)
            break
        
        citations_for_llm.append((citation, trimmed_quote))
        total_quote_chars += len(trimmed_quote)
    
    if len(citations_for_llm) == 0:
        context_text = "【引用】\n引用が見つかりませんでした。"
    else:
        context_parts = ["【引用】"]
        for i, (citation, trimmed_quote) in enumerate(citations_for_llm, 1):
            source_info = citation.source
            if citation.page is not None:
                source_info = f"{citation.source} (p.{citation.page})"
            
            context_parts.append(f"{i}. [{source_info}]\n{trimmed_quote}")
        
        context_text = "\n\n".join(context_parts)
    
    # levelごとのテンプレート指定（2個のみ）
    level_templates = {
        "beginner": "T3またはT4",
        "intermediate": "T6またはT7",
        "advanced": "T10またはT11",
    }
    allowed_templates = level_templates.get(level, "T3またはT4")
    
    # topicの扱い
    topic_text = f"トピック: {topic}\n" if topic else ""
    
    # userプロンプト（簡潔版、短い出力を強制）
    user_content = f"""JSONのみ出力。説明文禁止。

条件:
{topic_text}難易度: {level}
問題数: {count}個（短い出力で確実に返す）
使用テンプレート: {allowed_templates}

{context_text}

要求:
- quizzes配列に{count}個含める
- statementは{allowed_templates}のテンプレートに従う
- answer_boolは全てtrue
- explanationは1文のみ、最大80文字
- 引用に基づく事実のみ（推測禁止）
- 曖昧表現禁止（場合がある、望ましい等）

{{ "quizzes": [...] }}のみ出力。短く書く。"""
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    # プロンプト統計情報を計算（LLM負担の計測用）
    full_prompt = system_content + "\n\n" + user_content
    prompt_stats = {
        "llm_prompt_chars": len(full_prompt),
        "llm_prompt_preview_head": full_prompt[:200],
        "llm_input_citations_count": len(citations_for_llm),
        "llm_input_total_quote_chars": total_quote_chars,
    }
    
    return messages, prompt_stats


def build_quiz_json_fix_messages(
    level: Literal["beginner", "intermediate", "advanced"],
    count: int,
    topic: str | None,
    citations: List[Citation],
    previous_error: str,
) -> List[dict[str, str]]:
    """
    Quiz JSON修復用のメッセージリストを構築（簡潔版）
    
    Args:
        level: 難易度
        count: 生成するクイズの数
        topic: トピック
        citations: 引用リスト
        previous_error: 前回のエラー内容
        
    Returns:
        LLM用メッセージリスト
    """
    # systemプロンプト：JSON修復専用（簡潔版）
    system_content = f"""前回の出力はJSONエラーでした。修正して再出力してください。

必須:
- JSONのみ（説明文・コードフェンス禁止）
- quizzes配列に{count}個含める
- type: "true_false"
- answer_bool: true（bool値）
- 全角引用符禁止、カンマ・括弧の閉じ忘れ禁止

前回エラー: {previous_error}"""

    # citationsを制限・整形（厳格なタイムアウト対策）
    from app.core.settings import settings
    
    # LLMへ渡すcitations数を制限
    max_citations = settings.quiz_context_top_n
    max_quote_len = settings.quiz_quote_max_len
    max_total_chars = settings.quiz_total_quote_max_chars
    
    # citations数を制限し、total_quote_charsが上限を超えないように調整
    citations_for_llm = []
    total_quote_chars = 0
    
    for citation in citations[:max_citations]:
        # quoteをトリム
        trimmed_quote = citation.quote[:max_quote_len] if len(citation.quote) > max_quote_len else citation.quote
        
        # 総文字数チェック
        if total_quote_chars + len(trimmed_quote) > max_total_chars:
            # 上限を超える場合は、残り分だけ追加して終了
            remaining = max_total_chars - total_quote_chars
            if remaining > 50:  # 最低50文字ないと意味がないので追加しない
                trimmed_quote = trimmed_quote[:remaining]
                citations_for_llm.append((citation, trimmed_quote))
                total_quote_chars += len(trimmed_quote)
            break
        
        citations_for_llm.append((citation, trimmed_quote))
        total_quote_chars += len(trimmed_quote)
    
    if len(citations_for_llm) == 0:
        context_text = "引用なし"
    else:
        context_parts = []
        for i, (citation, trimmed_quote) in enumerate(citations_for_llm, 1):
            source_info = citation.source
            if citation.page is not None:
                source_info = f"{citation.source} (p.{citation.page})"
            
            context_parts.append(f"{i}. {source_info}: {trimmed_quote}")
        context_text = "\n".join(context_parts)
    
    # topicの扱い
    topic_text = f"トピック: {topic}\n" if topic else ""
    
    # userプロンプト（簡潔版）
    user_content = f"""JSONのみ出力。

{topic_text}難易度: {level}
問題数: {count}個
explanationは1文のみ、最大80文字

{context_text}

{{"quizzes":[...]}}のみ出力。短く書く。"""
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    return messages
