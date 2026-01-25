"""
重複チェック機能

【初心者向け】
- statement（問題文）の重複を検出する機能
- 正規化（空白・句読点除去）とコア内容キー（否定語除去）の2段階でチェック
- citation（出題箇所）の重複もチェック
"""
import logging
import re

from app.schemas.common import Citation

# ロガー設定
logger = logging.getLogger(__name__)


def normalize_statement(statement: str) -> str:
    """
    statementを正規化して比較用に使用
    
    【初心者向け】
    同じ意味の文でも、空白や句読点の有無で異なる文字列として扱われてしまうのを防ぐため、
    比較用に正規化（統一）します。
    
    処理内容:
    1. 空白を全て除去（例: "地震時 は" → "地震時は"）
    2. 句読点を除去（例: "地震時は。" → "地震時は"）
    3. 小文字に変換（英語の場合）
    
    Args:
        statement: クイズのstatement（問題文）
        
    Returns:
        正規化されたstatement（空白除去、句読点統一、小文字化）
        
    Example:
        "地震時 は、最初に身を守る。" → "地震時は最初に身を守る"
    """
    # ステップ1: 空白を全て除去（複数の空白も1つに統一）
    normalized = re.sub(r'\s+', '', statement)
    # ステップ2: 句読点を除去（日本語・英語の句読点に対応）
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    # ステップ3: 小文字に変換（英語の場合）
    return normalized.lower()


def get_core_content_key(statement: str) -> str:
    """
    コア内容キーを取得（否定語除去後の正規化）
    
    【初心者向け】
    同じ内容でも、肯定形と否定形で異なる文として扱われてしまうのを防ぐため、
    否定語を除去した「コア内容」のみで比較します。
    
    例:
    - "地震時は身を守る行動をとる。" → コア内容: "地震時は身を守る行動をとる"
    - "地震時は身を守る行動をとらない。" → コア内容: "地震時は身を守る行動をとる"（「とらない」を除去）
    
    これにより、「行う/行わない」の単純反転が同一セットに混入しないようにします。
    
    Args:
        statement: クイズのstatement（問題文）
        
    Returns:
        コア内容キー（否定語除去後の正規化された文字列）
    """
    # 否定語パターン（優先度順）
    negation_patterns = [
        r'しない',
        r'行わない',
        r'ではない',
        r'なくてもよい',
        r'禁止',
        r'不要',
        r'してはいけない',
        r'行ってはいけない',
        r'してはならない',
        r'行ってはならない',
    ]
    
    # 否定語を除去
    core = statement
    for pattern in negation_patterns:
        core = re.sub(pattern, '', core)
    
    # 正規化（空白除去、句読点除去、小文字化）
    normalized = re.sub(r'\s+', '', core)
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    return normalized.lower()


def is_duplicate_statement(new_statement: str, existing_statements: list[str]) -> bool:
    """
    新しいstatementが既存のものと重複しているかチェック
    
    【初心者向け】
    同じ問題が複数回生成されるのを防ぐため、重複チェックを行います。
    重複判定は2段階で行い、より厳密にチェックします。
    
    処理の流れ:
    1. 通常の正規化（空白・句読点除去）で完全一致チェック
       → 例: "地震時は身を守る。" と "地震時は身を守る" は同じと判定
    2. コア内容キー（否定語除去後）で一致チェック
       → 例: "地震時は身を守る。" と "地震時は身を守らない。" は同じと判定（単純反転を検出）
    
    Args:
        new_statement: 新しいstatement（チェック対象の問題文）
        existing_statements: 既存のstatementリスト（既に採用された問題文のリスト）
        
    Returns:
        True: 重複している（既に同じ問題が存在する）
        False: 重複していない（新しい問題）
    """
    # 【ステップ1】通常の正規化で完全一致チェック
    # 空白や句読点の違いを無視して、文字列が完全に一致するか確認
    normalized_new = normalize_statement(new_statement)
    for existing in existing_statements:
        normalized_existing = normalize_statement(existing)
        if normalized_new == normalized_existing:
            logger.info(f"重複検出（完全一致）: '{new_statement[:50]}...' と '{existing[:50]}...' が重複しています")
            return True
    
    # 【ステップ2】コア内容キー（否定語除去後）で一致チェック
    # 肯定形と否定形の単純反転を検出（例: "行う" と "行わない" は同じと判定）
    core_key_new = get_core_content_key(new_statement)
    for existing in existing_statements:
        core_key_existing = get_core_content_key(existing)
        # 空文字列は除外（正規化で全て除去された場合は重複としない）
        if core_key_new == core_key_existing and core_key_new:
            logger.info(f"重複検出（コア内容一致）: '{new_statement[:50]}...' と '{existing[:50]}...' がコア内容で重複しています")
            return True
    
    # 重複していない
    return False


def is_citation_duplicate(quiz_citations: list[Citation], used_citation_keys: set) -> bool:
    """
    クイズのcitationsが既に使用済みかチェック
    
    Args:
        quiz_citations: クイズのcitationsリスト
        used_citation_keys: 使用済みcitationキーのセット
        
    Returns:
        True: 重複している（既に使用済みのcitationを含む）、False: 重複していない
    """
    for citation in quiz_citations:
        citation_key = (
            citation.source,
            citation.page,
            citation.quote[:60] if citation.quote else ""
        )
        if citation_key in used_citation_keys:
            # TypeError対策: pageを文字列に変換
            page_str = str(citation.page) if citation.page is not None else "None"
            logger.info(
                f"出題箇所重複検出: '{citation.source}' (p.{page_str}) は既に使用済みです"
            )
            return True
    return False
