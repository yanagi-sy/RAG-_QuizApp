"""
N-gram検索（日本語対応フォールバック）
"""
import re
from typing import Set


def normalize(text: str) -> str:
    """
    テキストを正規化する
    
    - 改行・連続空白を詰める
    - 小文字化
    - 全角/半角の簡易統一（スペースのみ）
    
    Args:
        text: 元のテキスト
        
    Returns:
        正規化されたテキスト
    """
    # 改行を空白に置換
    normalized = text.replace("\n", " ").replace("\r", " ")
    
    # 連続する空白を1つに
    normalized = re.sub(r"\s+", " ", normalized)
    
    # 小文字化
    normalized = normalized.lower()
    
    # 全角スペースを半角スペースに統一
    normalized = normalized.replace("　", " ")
    
    # 前後の空白を削除
    normalized = normalized.strip()
    
    return normalized


def ngrams(text: str, n: int = 2) -> Set[str]:
    """
    テキストからN-gram集合を生成する
    
    - スペースを除去した文字列からN-gramを作る
    - 重複を排除するためSetを返す
    
    Args:
        text: 元のテキスト
        n: N-gramのN（デフォルト2）
        
    Returns:
        N-gramの集合
    """
    # 正規化（スペース除去）
    normalized = normalize(text)
    # スペースを除去
    normalized = normalized.replace(" ", "")
    
    # N-gramを生成
    grams: Set[str] = set()
    
    if len(normalized) < n:
        # 文字列が短すぎる場合は空集合を返す
        return grams
    
    for i in range(len(normalized) - n + 1):
        gram = normalized[i:i + n]
        grams.add(gram)
    
    return grams


def score(query: str, text: str) -> int:
    """
    クエリとテキストの一致スコアを計算する
    
    - クエリの2-gram集合とテキストの2-gram集合の重なり数（intersection）
    - 完全部分一致がある場合はボーナス加点（+100）
    
    Args:
        query: 検索クエリ
        text: 検索対象テキスト
        
    Returns:
        スコア（0以上）
    """
    # 2-gram集合を取得
    query_grams = ngrams(query, n=2)
    text_grams = ngrams(text, n=2)
    
    # 重なり数を計算
    intersection = query_grams & text_grams
    base_score = len(intersection)
    
    # 完全部分一致のチェック（正規化後のテキストで）
    normalized_query = normalize(query).replace(" ", "")
    normalized_text = normalize(text).replace(" ", "")
    
    if normalized_query in normalized_text:
        base_score += 100
    
    return base_score
