"""
statementで再検索し根拠（citations）を再付与する

citationsが空の場合、fallbackの代わりにstatementをクエリとして
ハイブリッド検索し、単一ソース制約を維持したまま根拠を付与する。
"""
import logging
from typing import List, Optional

from app.schemas.common import Citation
from app.rag.hybrid_retrieval import hybrid_retrieval

logger = logging.getLogger(__name__)

# 再検索時のtop_k（根拠として十分な件数）
DEFAULT_TOP_K = 3


def search_citations_for_statement(
    statement: str,
    source_ids: Optional[List[str]],
    top_k: int = DEFAULT_TOP_K,
) -> List[Citation]:
    """
    statementをクエリとしてハイブリッド検索し、引用リストを返す
    
    citationsが空のquizに対して、fallbackの代わりに使用する。
    単一ソース指定時はsource_filterで制約し、混入を防ぐ。
    
    Args:
        statement: クイズの断言文（検索クエリ）
        source_ids: 対象ソース（Noneなら全資料）
        top_k: 取得件数（デフォルト3）
        
    Returns:
        Citationのリスト（0件の場合は空リスト）
    """
    if not statement or not statement.strip():
        logger.warning("[CitationMatcher] statementが空のためスキップ")
        return []
    
    try:
        citations, _, _ = hybrid_retrieval(
            query=statement.strip(),
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=top_k,
            include_debug=False,
            source_filter=source_ids,
        )
        if citations:
            logger.info(
                f"[CitationMatcher] statement再検索で{len(citations)}件取得: "
                f"'{statement[:40]}...'"
            )
        return citations
    except Exception as e:
        logger.warning(f"[CitationMatcher] statement再検索失敗: {type(e).__name__}: {e}")
        return []
