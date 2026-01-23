"""
重複チェックロジック

クイズのstatementとcitationの重複をチェックする。
"""
import logging
import re
import unicodedata

from app.schemas.common import Citation

# ロガー設定
logger = logging.getLogger(__name__)


def normalize_statement(statement: str) -> str:
    """
    statementを正規化して比較用に使用
    
    Args:
        statement: クイズのstatement
        
    Returns:
        正規化されたstatement（空白除去、句読点統一、小文字化）
    """
    # 空白を除去
    normalized = re.sub(r'\s+', '', statement)
    # 句読点を統一（句読点を除去）
    normalized = normalized.replace('。', '').replace('、', '').replace('.', '').replace(',', '')
    return normalized.lower()


def get_core_content_key(statement: str) -> str:
    """
    コア内容キーを取得（否定語除去後の正規化）
    
    重複判定用に、否定語（しない/行わない/禁止/不要/ではない等）を除去した
    コア内容のみで比較する。これにより「行う/行わない」の単純反転が
    同一セットに混入しないようにする。
    
    Args:
        statement: クイズのstatement
        
    Returns:
        コア内容キー（否定語除去後の正規化）
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
    
    重複判定は2段階で行う:
    1. 通常の正規化（空白・句読点除去）で完全一致チェック
    2. コア内容キー（否定語除去後）で一致チェック（「行う/行わない」の単純反転を検出）
    
    Args:
        new_statement: 新しいstatement
        existing_statements: 既存のstatementリスト
        
    Returns:
        True: 重複している、False: 重複していない
    """
    # 1. 通常の正規化で完全一致チェック
    normalized_new = normalize_statement(new_statement)
    for existing in existing_statements:
        normalized_existing = normalize_statement(existing)
        if normalized_new == normalized_existing:
            logger.info(f"重複検出（完全一致）: '{new_statement[:50]}...' と '{existing[:50]}...' が重複しています")
            return True
    
    # 2. コア内容キー（否定語除去後）で一致チェック
    core_key_new = get_core_content_key(new_statement)
    for existing in existing_statements:
        core_key_existing = get_core_content_key(existing)
        if core_key_new == core_key_existing and core_key_new:  # 空文字列は除外
            logger.info(f"重複検出（コア内容一致）: '{new_statement[:50]}...' と '{existing[:50]}...' がコア内容で重複しています")
            return True
    
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


def create_citation_key(citation: Citation) -> tuple:
    """
    citationから重複チェック用のキーを生成
    
    Args:
        citation: Citationオブジェクト
        
    Returns:
        (source, page, quote_prefix) のタプル
    """
    return (
        citation.source,
        citation.page,
        citation.quote[:60] if citation.quote else ""
    )
