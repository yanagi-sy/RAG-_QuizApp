"""
クイズのバリデーション
"""

# 曖昧表現リスト（○×として判定不能な表現）
AMBIGUOUS_PHRASES = [
    "場合がある",
    "ことがある",
    "かもしれない",
    "望ましい",
    "推奨",
    "基本的に",
    "状況による",
    "適宜",
    "必要に応じて",
    "問題になっていない",
    "問題にならない",
    "一般的に",
    "通常は",
    "原則として",
    "できる限り",
    "なるべく",
    "できれば",
    "好ましい",
    "望ましくない",
    "考えられる",
    "思われる",
    "みられる",
]


def validate_quiz_item(item: dict) -> tuple[bool, str]:
    """
    クイズアイテムをバリデーション（○×問題専用、厳格版）
    
    検証項目:
    - type が "true_false" であること
    - statement が断言文であること（疑問形禁止）
    - statement が十分な長さであること（12文字以上）
    - statement に曖昧表現が含まれないこと
    - answer_bool が bool であること
    - citations が1件以上あること
    - citations の source/page/quote が欠けていないこと
    
    Args:
        item: クイズアイテム（dict）
        
    Returns:
        (ok: bool, reason: str) のタプル
        - ok: バリデーション結果（True=合格、False=不合格）
        - reason: 不合格の理由（合格時は空文字）
    """
    # type チェック
    if item.get("type") != "true_false":
        return (False, f"invalid_type:{item.get('type')}")
    
    # statement チェック（必須、文字列）
    statement = item.get("statement")
    if not statement or not isinstance(statement, str):
        return (False, "empty_statement")
    
    # statement の長さチェック（12文字未満は短すぎ）
    if len(statement.strip()) < 12:
        return (False, f"too_short:{len(statement.strip())}chars")
    
    # 疑問形チェック（?, ？, でしょうか, ですか）
    if "?" in statement or "？" in statement:
        return (False, "contains_question_mark")
    
    if statement.endswith("でしょうか") or statement.endswith("ですか"):
        return (False, "question_form_ending")
    
    # 曖昧表現チェック（○×として判定不能）
    for phrase in AMBIGUOUS_PHRASES:
        if phrase in statement:
            return (False, f"ambiguous_phrase:{phrase}")
    
    # answer_bool チェック（必須、bool型）
    answer_bool = item.get("answer_bool")
    if answer_bool is None or not isinstance(answer_bool, bool):
        return (False, f"invalid_answer_bool:{type(answer_bool).__name__}")
    
    # citations チェック（1件以上）
    citations = item.get("citations")
    if not citations or not isinstance(citations, list) or len(citations) == 0:
        return (False, "no_citations")
    
    # citations の中身をチェック
    for i, cit in enumerate(citations):
        if not isinstance(cit, dict):
            return (False, f"invalid_citation_type:index={i}")
        
        if not cit.get("source"):
            return (False, f"missing_citation_source:index={i}")
        
        if not cit.get("quote"):
            return (False, f"missing_citation_quote:index={i}")
        
        # page は null でも OK（txt の場合）
    
    return (True, "")
