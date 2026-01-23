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
    banned_statements: List[str] | None = None,
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
        banned_statements: 出力禁止のstatementリスト（既出・重複で落としたもの）
        
    Returns:
        (LLM用メッセージリスト, プロンプト統計情報)
    """
    # systemプロンプト：理解度を深めるクイズ生成版
    system_content = """業務マニュアルから理解度を深めるクイズを作成します。

【重要】言語ルール:
- すべての出力は日本語で行うこと
- statement、explanation、すべてのテキストは必ず日本語で出力すること
- 英語での出力は一切禁止

出力ルール:
- JSONのみ出力（説明文・コードフェンス・コメント禁止）
- { "quizzes": [...] } の形式のみ
- quizzes配列は指定個数を必ず含める

各quizの必須要素:
- type: "true_false"
- statement: 下記テンプレートのいずれかに従う断言文（必ず肯定文のみ）
- answer_bool: true（常にtrue）
- explanation: 理解を深める説明（理由・背景・重要性を含む、最大120文字）
- citations: 入力で渡された引用をそのまま使用

難易度別の出題方針:
【初級（beginner）】基本的事実の確認
- 何をすべきか、基本的なルールや手順を問う
- テンプレート: T3, T4

【中級（intermediate）】理由・方法・適用場面を問う
- なぜその行為が必要か、どのように行うか、どの場面で適用するかを問う
- テンプレート: T6, T7, T8, T9

【上級（advanced）】例外・判断基準・リスクを問う
- 例外ケース、判断基準、リスク管理、複合的な理解を問う
- テンプレート: T10, T11, T12, T13

statementテンプレート（肯定文のみ、文脈を含む）:
【重要】すべてのstatementには、状況・条件・タイミングなどの文脈を含めること。
単純な「【対象】では【行為】を行う」ではなく、「【状況】の場合、【対象】では【行為】を行う」のように文脈を明確にする。

【初級】
T3: 「【状況・条件】の場合、【主体】は【行為】を必ず行う。」
  例: 「火災が発生した場合、店舗スタッフは避難誘導を行う。」
T4: 「【タイミング・場面】において、【主体】は【基本ルール】に従って【行為】を行う。」
  例: 「緊急時において、店舗スタッフは安全マニュアルに従って避難誘導を行う。」

【中級】
T6: 「【条件】の場合、【主体】は【行為】を行い、その後【確認】を行う。」
  例: 「高齢者や子どもがいる場合、店舗スタッフは避難誘導を行い、その後全員の避難を確認する。」
T7: 「【操作】の前に【主体】は【前提条件・状況】を確認する必要がある。」
  例: 「避難誘導を開始する前に、店舗スタッフは店内の状況と避難経路を確認する必要がある。」
T8: 「【状況・条件】の場合、【主体】は【行為】を行う。その理由は【理由】である。」
  例: 「緊急時において、店舗スタッフは避難誘導を行う。その理由は、迅速な避難を確保するためである。」
T9: 「【状況A】の場合は【主体】は【行為A】を行い、【状況B】の場合は【行為B】を行う。」
  例: 「通常時においては店舗スタッフは通常の誘導を行うが、緊急時においては優先的に避難誘導を行う。」

【上級】
T10: 「【条件・状況】がある場合、【主体】は【対応行為】を行う。」
  例: 「火災警報が鳴った場合、店舗スタッフは避難誘導を行う。」
T11: 「【判断条件・状況】に該当する場合、【主体】は【対応】を行う必要がある。」
  例: 「高齢者や子どもが店内にいる状況に該当する場合、店舗スタッフは避難誘導を行う必要がある。」
T12: 「【通常ケース・状況】では【主体】は【通常行為】を行うが、【例外条件・状況】の場合は【例外行為】を行う。」
  例: 「通常時においては店舗スタッフは通常の誘導を行うが、緊急時においては優先的に避難誘導を行う。」
T13: 「【判断基準1・状況】かつ【判断基準2・状況】に該当する場合、【主体】は【対応】を行う必要がある。」
  例: 「火災警報が鳴った状況かつ高齢者がいる状況に該当する場合、店舗スタッフは避難誘導を行う必要がある。」

重要ルール:
1. statementは必ず肯定文のみ（「する」「行う」「確認する」など）
2. 【必須】すべてのstatementには文脈（状況・条件・タイミング・場面）を含めること:
   - 「【対象】では【行為】を行う」ではなく、「【状況】の場合、【対象】では【行為】を行う」のように文脈を明確にする
   - 状況: 火災が発生した場合、緊急時、通常時、異常が検出された場合など
   - 条件: 高齢者がいる場合、警報が鳴った場合、特定の条件が満たされた場合など
   - タイミング: 作業開始前、作業中、作業終了後、定期的になど
   - 場面: 店内、店外、バックヤード、フロアなど
3. 禁止事項（「してはならない」など）が引用にある場合:
   - 「必ず【逆の行為】を行う」に変換し、状況・条件を含める
   - 例: 「二重書き込みをしてはならない」→「ファイル編集時において、必ず一人で行う」
4. 否定形・禁止表現は一切使わない（してはならない、禁止、NG、ダメ、しない、ではない）
5. explanationは理解を深める内容にする:
   - 初級: 基本的な理由や重要性を簡潔に、状況・条件も含めて説明
   - 中級: 具体的な理由、方法、適用場面を説明、なぜその状況でその行為が必要かを説明
   - 上級: 例外ケース、判断基準、リスク管理の観点を含める、複合的な状況での判断を説明

禁止表現（絶対に使わない）:
- 疑問形（?、ですか、でしょうか）
- 否定形（してはならない、行ってはならない、禁止、NG、ダメ、しない、ではない、必要ない）
- 曖昧表現（場合がある、望ましい、基本的に、状況による、適宜、推奨）

テンプレートの【】部分は引用から抽出。引用に無い情報は追加しない。
理解度を深めるため、単純な事実確認ではなく、理由・方法・判断基準を含む内容を優先する。

【文脈を含める例】
❌ 悪い例: 「店内では避難誘導を行う。」（文脈が不明確：いつ？誰が？）
✅ 良い例: 「火災が発生した場合、店舗スタッフは避難誘導を行う。」（状況と主体が明確）
✅ 良い例: 「緊急時において、高齢者や子どもがいる場合、店舗スタッフは優先的に避難誘導を行う。」（状況・条件・主体が明確）

文脈（状況・条件・タイミング）を含めることで、どのような時にどうする/しないかが明確になり、理解度が深まります。

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
    
    # levelごとのテンプレート指定（理解度を深める形式）
    level_templates = {
        "beginner": "T3またはT4（基本的事実の確認）",
        "intermediate": "T6、T7、T8、T9のいずれか（理由・方法・適用場面を問う）",
        "advanced": "T10、T11、T12、T13のいずれか（例外・判断基準・リスクを問う）",
    }
    allowed_templates = level_templates.get(level, "T3またはT4")
    
    # levelごとの説明方針
    explanation_guidance = {
        "beginner": "基本的な理由や重要性を簡潔に説明（最大100文字）",
        "intermediate": "具体的な理由、方法、適用場面を説明（最大120文字）",
        "advanced": "例外ケース、判断基準、リスク管理の観点を含めて説明（最大150文字）",
    }
    explanation_guide = explanation_guidance.get(level, "基本的な理由や重要性を簡潔に説明")
    
    # topicの扱い
    topic_text = f"トピック: {topic}\n" if topic else ""
    
    # userプロンプト（理解度を深める版）
    user_content = f"""JSONのみ出力。説明文禁止。

【重要】言語ルール:
- すべての出力は日本語で行うこと
- statement、explanation、すべてのテキストは必ず日本語で出力すること
- 英語での出力は一切禁止

条件:
{topic_text}難易度: {level}
問題数: {count}個（短い出力で確実に返す）
使用テンプレート: {allowed_templates}

{context_text}

要求:
- quizzes配列に{count}個含める
- statementは{allowed_templates}のテンプレートに従う（必ず肯定文のみ）
- answer_boolは全てtrue
- explanationは{explanation_guide}
- 引用に基づく事実のみ（推測禁止）
- 曖昧表現禁止（場合がある、望ましい等）
- 否定形・禁止表現は一切使わない（「してはならない」「禁止」などは絶対に使わない）

理解度を深める方針:
- 単純な事実確認ではなく、理由・方法・判断基準を含む内容を優先する
- 【必須】すべてのstatementには文脈（状況・条件・タイミング・場面）を含めること
- 初級: 基本的なルールや手順を明確に、どのような状況で適用するかを示す
- 中級: なぜその行為が必要か、どのように行うか、どの状況で適用するかを説明
- 上級: 例外ケース、判断基準、リスク管理の観点を含める、複合的な状況での判断を示す

【文脈を含める重要性】
- 「店内では避難誘導を行う」→ 文脈が不明確（いつ？誰が？）
- 「火災が発生した場合、店舗スタッフは避難誘導を行う」→ 文脈が明確（緊急時、主体が明確）
- 「緊急時において、高齢者や子どもがいる場合、店舗スタッフは優先的に避難誘導を行う」→ より具体的な文脈（緊急時、条件・主体が明確）

重要: 引用に「してはならない」などの禁止表現があっても、statementでは必ず肯定文に変換すること。
例: 引用が「二重書き込みをしてはならない」の場合、statementは「ファイル編集時は必ず一人で行う」のように肯定文にする。

"""
    
    # banned_statementsをプロンプトに追加
    banned_section = ""
    if banned_statements and len(banned_statements) > 0:
        banned_list = "\n".join(f"- {s[:80]}..." if len(s) > 80 else f"- {s}" for s in banned_statements[:30])
        banned_section = f"\n\n[出力禁止] 以下のstatementは既に生成済みまたは重複で除外されたため、同一/類似のstatementを出力しないこと:\n{banned_list}\n"
    
    user_content = user_content + banned_section + "\n{{ \"quizzes\": [...] }}のみ出力。短く書く。"""
    
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
    # systemプロンプト：JSON修復専用（簡潔版、文脈を含める指示も追加）
    system_content = f"""前回の出力はJSONエラーでした。修正して再出力してください。

【重要】言語ルール:
- すべての出力は日本語で行うこと
- statement、explanation、すべてのテキストは必ず日本語で出力すること
- 英語での出力は一切禁止

必須:
- JSONのみ（説明文・コードフェンス禁止）
- quizzes配列に{count}個含める
- type: "true_false"
- answer_bool: true（bool値）
- 全角引用符禁止、カンマ・括弧の閉じ忘れ禁止
- 【重要】statementには必ず文脈（状況・条件・タイミング・場面）を含めること
  - 例: 「火災が発生した場合、店舗スタッフは出口へ避難誘導を行う。」
  - ❌ 悪い例: 「店内では避難誘導を行う。」（文脈が不明確）

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
    
    # userプロンプト（簡潔版、理解度を深める説明を含む）
    explanation_guidance_fix = {
        "beginner": "基本的な理由や重要性を簡潔に説明（最大100文字）",
        "intermediate": "具体的な理由、方法、適用場面を説明（最大120文字）",
        "advanced": "例外ケース、判断基準、リスク管理の観点を含めて説明（最大150文字）",
    }
    explanation_guide_fix = explanation_guidance_fix.get(level, "基本的な理由や重要性を簡潔に説明（最大100文字）")
    
    user_content = f"""JSONのみ出力。

【重要】言語ルール:
- すべての出力は日本語で行うこと
- statement、explanation、すべてのテキストは必ず日本語で出力すること
- 英語での出力は一切禁止

{topic_text}難易度: {level}
問題数: {count}個
explanationは{explanation_guide_fix}

{context_text}

{{"quizzes":[...]}}のみ出力。短く書く。"""
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    return messages
