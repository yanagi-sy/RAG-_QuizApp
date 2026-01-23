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
- type: "true_false"（必ずこの文字列。テンプレート名（T3、T6など）ではない）
- statement: 下記テンプレートのいずれかに従う断言文（必ず肯定文のみ、日本語のみ）
- answer_bool: true（常にtrue）
- explanation: 理解を深める説明（理由・背景・重要性を含む、最大120文字、日本語のみ）
- citations: 入力で渡された引用をそのまま使用（dict形式: {"source": "...", "page": ..., "quote": "..."}）

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

【基本文型】すべてのstatementは「いつ・誰が・何を・どうする」の形式に基づいて作成してください。
- いつ: 引用に記載されている具体的な状況・条件・タイミング（例：「作業開始時」「異常が検出された時」「特定の条件が満たされた時」）
- 誰が: 引用に記載されている主体（例：「担当者」「スタッフ」「作業員」）
- 何を: 引用に記載されている対象・目的（例：「機器」「設備」「書類」）
- どうする: 引用に記載されている行為・手順（例：「確認する」「報告する」「対応する」）

【重要】前提条件は抽象的（「異常が検出された場合」など）ではなく、引用に記載されている具体的な状況・条件を使用してください。

【初級】
T3: 「【具体的な状況・条件】の場合、【引用に記載されている主体】は【引用に記載されている行為】を必ず行う。」
  例: 「清掃作業開始時において、清掃担当者は清掃用具を準備する。」
  注意: 「異常が検出された場合」などの抽象的な表現は使わず、引用に記載されている具体的な状況を使用する。

T4: 「【引用に記載されているタイミング・場面】において、【引用に記載されている主体】は【引用に記載されている基本ルール】に従って【引用に記載されている行為】を行う。」
  例: 「作業開始時において、作業員は安全マニュアルに従って安全確認を行う。」
  注意: 引用に記載されている具体的なタイミング・場面・ルールを使用する。

【中級】
T6: 「【引用に記載されている具体的な条件】の場合、【引用に記載されている主体】は【引用に記載されている行為】を行い、その後【引用に記載されている確認】を行う。」
  例: 「機器の異常が検出された場合、担当者は緊急停止ボタンを押し、その後管理者に報告する。」
  注意: 「特定の条件」などの抽象的な表現は使わず、引用に記載されている具体的な条件を使用する。

T7: 「【引用に記載されている操作】の前に【引用に記載されている主体】は【引用に記載されている前提条件・状況】を確認する必要がある。」
  例: 「清掃作業を開始する前に、清掃担当者は清掃用具の点検を行う必要がある。」
  注意: 引用に記載されている具体的な操作・前提条件を使用する。

T8: 「【引用に記載されている具体的な状況・条件】の場合、【引用に記載されている主体】は【引用に記載されている行為】を行う。その理由は【引用に記載されている理由】である。」
  例: 「機器の温度が設定値を超えた場合、担当者は緊急停止を行う。その理由は、機器の損傷を防ぐためである。」
  注意: 引用に記載されている具体的な状況・理由を使用する。

T9: 「【引用に記載されている状況A】の場合は【引用に記載されている主体】は【引用に記載されている行為A】を行い、【引用に記載されている状況B】の場合は【引用に記載されている行為B】を行う。」
  例: 「通常の清掃作業においては清掃担当者は通常の清掃用具を使用するが、特別な汚れがある場合は専用の清掃用具を使用する。」
  注意: 引用に記載されている具体的な状況・行為を使用する。

【上級】
T10: 「【引用に記載されている具体的な条件・状況】がある場合、【引用に記載されている主体】は【引用に記載されている対応行為】を行う。」
  例: 「機器の温度が設定値を超えた場合、担当者は緊急停止手順を実行する。」
  注意: 「警報が発報した場合」などの抽象的な表現は使わず、引用に記載されている具体的な条件を使用する。

T11: 「【引用に記載されている具体的な判断条件・状況】に該当する場合、【引用に記載されている主体】は【引用に記載されている対応】を行う必要がある。」
  例: 「機器の温度が設定値を超え、かつ警告音が鳴った状況に該当する場合、担当者は緊急停止を行う必要がある。」
  注意: 引用に記載されている具体的な判断条件を使用する。

T12: 「【引用に記載されている通常ケース・状況】では【引用に記載されている主体】は【引用に記載されている通常行為】を行うが、【引用に記載されている例外条件・状況】の場合は【引用に記載されている例外行為】を行う。」
  例: 「通常の清掃作業においては清掃担当者は通常の清掃用具を使用するが、油汚れがある場合は専用の清掃剤を使用する。」
  注意: 引用に記載されている具体的な通常ケース・例外条件を使用する。

T13: 「【引用に記載されている判断基準1・状況】かつ【引用に記載されている判断基準2・状況】に該当する場合、【引用に記載されている主体】は【引用に記載されている対応】を行う必要がある。」
  例: 「機器の温度が設定値を超えた状況かつ警告音が鳴った状況に該当する場合、担当者は緊急停止を行う必要がある。」
  注意: 引用に記載されている具体的な判断基準を使用する。

重要ルール:
1. statementは必ず肯定文のみ（「する」「行う」「確認する」など）、日本語のみ（英語禁止）
2. 【必須】すべてのstatementには文脈（状況・条件・タイミング・場面）を含めること:
   - 「【対象】では【行為】を行う」ではなく、「【状況】の場合、【対象】では【行為】を行う」のように文脈を明確にする
   - 状況: 引用に記載されている具体的な状況（例：「機器の温度が設定値を超えた場合」「清掃作業開始時」）
   - 条件: 引用に記載されている具体的な条件（例：「油汚れがある場合」「警告音が鳴った場合」）
   - タイミング: 引用に記載されている具体的なタイミング（例：「作業開始前」「作業終了後」「定期的に」）
   - 場面: 引用に記載されている具体的な場面（例：「店内」「店外」「バックヤード」）
   - 【重要】抽象的表現（「異常が検出された場合」「特定の条件が満たされた場合」など）は使わず、引用に記載されている具体的な表現を使用する
3. 【基本文型】すべてのstatementは「いつ・誰が・何を・どうする」の形式に基づいて作成する:
   - いつ: 引用に記載されている具体的な状況・条件・タイミング
   - 誰が: 引用に記載されている主体（担当者、スタッフ、作業員など）
   - 何を: 引用に記載されている対象・目的（機器、設備、書類など）
   - どうする: 引用に記載されている行為・手順（確認する、報告する、対応するなど）
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
【絶対禁止】引用に含まれていないキーワード（例：「火災」「避難」「災害」など）をstatementに追加しないでください。引用に記載されている内容のみを使用してください。
理解度を深めるため、単純な事実確認ではなく、理由・方法・判断基準を含む内容を優先する。

【文脈を含める例】
❌ 悪い例: 「担当者は対応を行う。」（文脈が不明確：いつ？どの状況で？）
✅ 良い例: 「異常が検出された場合、担当者は対応手順を実行する。」（状況と主体が明確）
✅ 良い例: 「緊急時において、特定の条件が満たされた場合、担当者は優先的に対応を行う。」（状況・条件・主体が明確）

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
    
    # 【品質担保】指定sourceのみを使用することを明示
    source_constraint = ""
    if citations and len(citations) > 0:
        # citationsのsourceを取得（重複排除）
        unique_sources = sorted(set(c.source for c in citations))
        if len(unique_sources) == 1:
            source_constraint = f"\n【重要】指定されたsourceのみを使用してください。\n指定source: {unique_sources[0]}\n他のsourceの内容を含めないでください。\n"
        elif len(unique_sources) > 1:
            source_constraint = f"\n【重要】指定されたsourceのみを使用してください。\n指定source: {', '.join(unique_sources)}\n他のsourceの内容を含めないでください。\n"
    
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
{source_constraint}
{context_text}

要求:
- quizzes配列に{count}個含める
- typeは必ず"true_false"（テンプレート名（T3、T6など）ではない）
- statementは{allowed_templates}のテンプレートに従う（必ず肯定文のみ、日本語のみ、英語禁止）
- answer_boolは全てtrue
- explanationは{explanation_guide}（日本語のみ、英語禁止）
- citationsはdict形式で指定（例: {{"source": "...", "page": ..., "quote": "..."}}）
- 引用に基づく事実のみ（推測禁止）
- 曖昧表現禁止（場合がある、望ましい等）
- 否定形・禁止表現は一切使わない（「してはならない」「禁止」などは絶対に使わない）
- 【重要】前提条件は抽象的（「異常が検出された場合」など）ではなく、引用に記載されている具体的な状況・条件を使用する
- 【重要】すべてのstatementは「いつ・誰が・何を・どうする」の形式に基づいて作成する

理解度を深める方針:
- 単純な事実確認ではなく、理由・方法・判断基準を含む内容を優先する
- 【必須】すべてのstatementには文脈（状況・条件・タイミング・場面）を含めること
- 初級: 基本的なルールや手順を明確に、どのような状況で適用するかを示す
- 中級: なぜその行為が必要か、どのように行うか、どの状況で適用するかを説明
- 上級: 例外ケース、判断基準、リスク管理の観点を含める、複合的な状況での判断を示す

【文脈を含める重要性】
- 「担当者は対応を行う」→ 文脈が不明確（いつ？どの状況で？）
- 「機器の温度が設定値を超えた場合、担当者は緊急停止を実行する」→ 文脈が明確（具体的な状況、主体が明確）
- 「清掃作業開始時において、油汚れがある場合、清掃担当者は専用の清掃剤を使用する」→ より具体的な文脈（具体的な状況、条件・主体が明確）

【重要】引用に含まれている内容のみを使用してください。引用に「火災」「避難」「災害」などのキーワードが含まれていない場合、これらのキーワードをstatementに追加しないでください。

【絶対禁止】
- 英語での生成（例：「In the event of...」など）は禁止。必ず日本語で生成してください。
- 抽象的表現（「異常が検出された場合」「特定の条件が満たされた場合」など）は禁止。引用に記載されている具体的な表現を使用してください。
- テンプレート名（T3、T6など）をtypeフィールドに入れないでください。typeは必ず"true_false"です。

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
  - 例: 「異常が検出された場合、担当者は対応手順を実行する。」
  - ❌ 悪い例: 「担当者は対応を行う。」（文脈が不明確）
- 【絶対禁止】引用に含まれていないキーワード（例：「火災」「避難」「災害」など）をstatementに追加しないでください。引用に記載されている内容のみを使用してください。

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
