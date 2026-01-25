"""
Embedding生成（テキスト→ベクトル変換）

【初心者向け】
- Embedding = 文や単語を数値ベクトル（例: 384次元）に変換したもの
- 似た意味の文は似たベクトルになるので、「意味で検索」するRAGの土台
- E5モデル: queryには "query: ", passageには "passage: " のprefixを付ける仕様
"""
import logging
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

# ロガー設定
logger = logging.getLogger(__name__)

# グローバルモデルインスタンス（起動時ロード）
_model: SentenceTransformer | None = None


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = "intfloat/multilingual-e5-small") -> SentenceTransformer:
    """
    Embeddingモデルを取得（シングルトン、起動時ロード）
    
    Args:
        model_name: モデル名（デフォルト: intfloat/multilingual-e5-small）
        
    Returns:
        SentenceTransformerインスタンス
    """
    global _model
    
    if _model is None:
        logger.info(f"Embeddingモデルをロード中: {model_name}")
        _model = SentenceTransformer(model_name)
        logger.info("Embeddingモデルのロード完了")
    
    # CHANGED: _model が既にロード済みでも必ず return _model（ifの外でreturn）
    return _model


def embed_texts(texts: List[str], model_name: str = "intfloat/multilingual-e5-small") -> List[List[float]]:
    """
    テキストリストをEmbeddingに変換
    
    Args:
        texts: テキストリスト
        model_name: モデル名
        
    Returns:
        Embeddingベクトルのリスト
    """
    model = get_embedding_model(model_name)
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def embed_passages(passages: List[str], model_name: str = "intfloat/multilingual-e5-small") -> List[List[float]]:
    """
    文書（passage）をEmbeddingに変換（E5のprefix付き）
    
    Args:
        passages: 文書テキストのリスト
        model_name: モデル名
        
    Returns:
        Embeddingベクトルのリスト
    """
    # E5の仕様に合わせてprefixを付ける
    prefixed_texts = [f"passage: {passage}" for passage in passages]
    return embed_texts(prefixed_texts, model_name)


def embed_query(query: str, model_name: str = "intfloat/multilingual-e5-small") -> List[float]:
    """
    質問（query）をEmbeddingに変換（E5のprefix付き）
    
    Args:
        query: 質問テキスト
        model_name: モデル名
        
    Returns:
        Embeddingベクトル
    """
    # E5の仕様に合わせてprefixを付ける
    prefixed_text = f"query: {query}"
    embeddings = embed_texts([prefixed_text], model_name)
    return embeddings[0]
