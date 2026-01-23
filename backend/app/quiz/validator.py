"""
クイズのバリデーション
"""
import re
import logging

# ロガー設定
logger = logging.getLogger(__name__)

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

# 不自然表現パターン（全ソース共通の簡易ルール）
# 過検知を避けるため、軽めのチェックのみ
UNNATURAL_PATTERNS = [
    # 客体ズレ: 「を優先して」は目的語が不自然（「へ優先的に」「を優先的に」が自然）
    (r"を優先して", "expression_unnatural_object"),
    # 指示語のみ: 「この/その/それ」だけでは内容が決まらない（文脈依存）
    # ただし、過検知を避けるため、単独で使われている場合のみ
    (r"^(この|その|それ)\s*[はがを]|^[はがを]\s*(この|その|それ)", "expression_ambiguous_reference"),
]

# 禁止表現パターン（クイズ文体を強制：断言文のみ許可）
# 「ください/お願いします/〜しないでください/〜してください/？/しましょう」等を禁止
FORBIDDEN_PHRASES = [
    "ください",
    "お願いします",
    "お願いいたします",
    "しないでください",
    "してください",
    "しましょう",
    "しましょうか",
    "して下さい",
    "して下さい。",
    "お願い",
    "？",  # 全角疑問符
    "?",   # 半角疑問符
]

# 禁止語パターン（引用に含まれる禁止表現）
# quoteに含まれる場合、statementが肯定形ならreject
FORBIDDEN_IN_QUOTE = [
    "やってはいけない",
    "禁止",
    "厳禁",
    "してはならない",
    "行ってはならない",
    "してはいけない",
    "行ってはいけない",
    "してはならない",
    "行ってはならない",
    "禁止されている",
    "禁止する",
    "禁止事項",
]

# 肯定形パターン（禁止語がある場合に肯定形かどうかを判定）
AFFIRMATIVE_PATTERNS = [
    r"する",
    r"行う",
    r"実行する",
    r"実施する",
    r"行うこと",
    r"すること",
]

# 否定語パターン（statementに含まれる場合、肯定形ではないと判定）
NEGATIVE_PATTERNS_IN_STATEMENT = [
    r"しない",
    r"行わない",
    r"してはいけない",
    r"行ってはいけない",
    r"禁止",
    r"厳禁",
    r"してはならない",
    r"行ってはならない",
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
    
    # 【品質担保】禁止表現チェック（クイズ文体を強制：断言文のみ許可）
    for phrase in FORBIDDEN_PHRASES:
        if phrase in statement:
            return (False, f"forbidden_phrase:{phrase}")
    
    # 【品質担保】statementは「。」で終わることを強制（必要なら整形）
    statement_stripped = statement.strip()
    if not statement_stripped.endswith("。"):
        # 「。」で終わっていない場合は追加（ただし、既に「?」「？」でreject済み）
        # ここでは「。」がない場合のみreject（整形は後処理で行う）
        return (False, "missing_period_end")
    
    # 曖昧表現チェック（○×として判定不能）
    for phrase in AMBIGUOUS_PHRASES:
        if phrase in statement:
            return (False, f"ambiguous_phrase:{phrase}")
    
    # 表現品質チェック（全ソース共通の簡易ルール）
    # 過検知を避けるため、軽めのチェックのみ
    for pattern, reason in UNNATURAL_PATTERNS:
        if re.search(pattern, statement):
            return (False, reason)
    
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
        
        quote = cit.get("quote")
        if not quote:
            return (False, f"missing_citation_quote:index={i}")
        
        # page は null でも OK（txt の場合）
        
        # 【品質担保】quoteに禁止語が含まれる場合、statementが肯定形ならreject
        quote_text = str(quote)
        has_forbidden_in_quote = any(forbidden in quote_text for forbidden in FORBIDDEN_IN_QUOTE)
        
        if has_forbidden_in_quote:
            # statementが肯定形かどうかをチェック
            is_affirmative = any(re.search(pattern, statement) for pattern in AFFIRMATIVE_PATTERNS)
            has_negative = any(re.search(pattern, statement) for pattern in NEGATIVE_PATTERNS_IN_STATEMENT)
            
            # 肯定形で、かつ否定語を含まない場合、禁止セクションと矛盾している
            if is_affirmative and not has_negative:
                logger.warning(
                    f"[VALIDATOR] 禁止語チェック失敗: quoteに禁止語があるのに、statementが肯定形で○になっています。"
                    f"quote_preview={quote_text[:60]}..., statement={statement[:60]}..."
                )
                return (False, "contradict_forbidden_section")
        
        # 【品質担保】quote中の重要語がstatementに含まれるかチェック
        # quoteから重要語を抽出（2文字以上の名詞・動詞を想定）
        # 簡易実装：quote中の主要な単語がstatementに含まれるかチェック
        # ただし、過検知を避けるため、quoteが短い場合（30文字未満）はスキップ
        if len(quote_text) >= 30:
            # quoteから主要な単語を抽出（ひらがな・カタカナ・漢字の連続、2文字以上）
            quote_words = re.findall(r'[ひらがなカタカナ漢字ー]{2,}', quote_text)
            # 2文字以上の単語のみを対象（ただし、一般的すぎる単語は除外）
            common_words = ["こと", "もの", "ため", "とき", "場合", "とき", "よう", "こと", "もの", "ため"]
            quote_keywords = [w for w in quote_words if len(w) >= 2 and w not in common_words]
            
            # statementに主要な単語が含まれているかチェック
            # ただし、quoteが長すぎる場合はスキップ（過検知防止）
            if len(quote_keywords) > 0 and len(quote_keywords) <= 10:
                # 主要な単語のうち、少なくとも1つがstatementに含まれているか
                found_keyword = False
                for keyword in quote_keywords[:5]:  # 最大5語までチェック
                    if keyword in statement:
                        found_keyword = True
                        break
                
                # 主要な単語が1つも含まれていない場合、根拠が弱い
                # ただし、quoteが長すぎる場合（100文字以上）はスキップ（過検知防止）
                if not found_keyword and len(quote_keywords) >= 2 and len(quote_text) < 100:
                    logger.warning(
                        f"[VALIDATOR] 重要語チェック失敗: quote中の主要な単語がstatementに含まれていません。"
                        f"quote_keywords={quote_keywords[:5]}, statement={statement[:60]}..."
                    )
                    return (False, "not_grounded_terms")
    
    return (True, "")
