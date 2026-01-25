"""
Cross-Encoder リランキング（QA用・検索精度向上）

【初心者向け】
- (query, document) のペアごとに関連度スコアを出し、候補を再ソートする
- Semantic検索の上位候補をさらに絞り込む用途。モデルは mmarco-mMiniLM 等
- 計算コストが高いため、候補を絞ってから適用する設計
"""
import logging
from typing import List, Tuple, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_cross_encoder(model_name: str):
    """
    Cross-Encoderモデルをロード（キャッシュ）
    
    Args:
        model_name: モデル名
        
    Returns:
        CrossEncoderモデル
    """
    try:
        from sentence_transformers import CrossEncoder
        
        logger.info(f"Cross-Encoderモデルをロード中: {model_name}")
        model = CrossEncoder(model_name)
        logger.info(f"Cross-Encoderモデルロード完了: {model_name}")
        return model
    except ImportError:
        logger.error("sentence-transformersがインストールされていません")
        raise
    except Exception as e:
        logger.error(f"Cross-Encoderモデルのロードに失敗: {type(e).__name__}: {e}")
        raise


def rerank_documents(
    query: str,
    documents: List[Tuple[str, any]],  # [(text, metadata), ...]
    model_name: str,
    top_n: Optional[int] = None,
    batch_size: int = 8,
) -> List[Tuple[str, any, float]]:
    """
    Cross-Encoderでドキュメントを再ランキング
    
    Args:
        query: 検索クエリ
        documents: [(text, metadata), ...] のリスト
        model_name: Cross-Encoderモデル名
        top_n: 上位N件を返す（Noneの場合は全件）
        batch_size: バッチサイズ
        
    Returns:
        [(text, metadata, rerank_score), ...] のリスト（スコア降順）
    """
    if len(documents) == 0:
        return []
    
    try:
        # モデルロード
        model = _load_cross_encoder(model_name)
        
        # クエリとドキュメントのペアを作成
        pairs = [(query, doc[0]) for doc in documents]
        
        # スコア計算
        scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
        
        # (text, metadata, score)のリストを作成
        results = [
            (doc[0], doc[1], float(score))
            for doc, score in zip(documents, scores)
        ]
        
        # スコア降順でソート
        results.sort(key=lambda x: x[2], reverse=True)
        
        # 上位N件を返す
        if top_n is not None:
            results = results[:top_n]
        
        logger.info(
            f"Cross-Encoderリランキング完了: input={len(documents)}, "
            f"top3_scores={[s for _, _, s in results[:3]]}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Cross-Encoderリランキングに失敗: {type(e).__name__}: {e}")
        # 失敗時は元の順序を維持（scoreは0.0）
        return [(doc[0], doc[1], 0.0) for doc in documents]
