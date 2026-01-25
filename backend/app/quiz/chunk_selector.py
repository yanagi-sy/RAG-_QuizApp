"""
Quiz専用 Chunk Selector（難易度に応じた出題点フィルタ）

【初心者向け】
- beginner: 概要/定義/目的/基本/ルール 等のキーワードでスコア
- intermediate: 手順/方法/対応/フロー/操作 等
- advanced: 例外/禁止/注意/判断/リスク 等
- 見出し・適度な長さにボーナス。top_n 件を選んで返す

chunk text を軽量スコアリングして、level別に出題に向く chunk を選ぶ。
LLM追加呼び出しなし。
"""
import logging
import re
import unicodedata
from typing import List, Dict, Tuple

# ロガー設定
logger = logging.getLogger(__name__)

# level別の優先キーワード（NFC正規化して判定、理解度を深める観点を追加）
LEVEL_KEYWORDS = {
    "beginner": {
        "概要": 3.0,
        "定義": 3.0,
        "目的": 2.5,
        "原則": 2.5,
        "基本": 2.0,
        "とは": 2.0,
        "ルール": 2.0,
        "重要性": 1.5,  # 理解を深める観点
        "理由": 1.0,  # 基本的な理由
    },
    "intermediate": {
        "手順": 3.0,
        "方法": 3.0,
        "対応": 2.5,
        "フロー": 2.5,
        "確認": 2.0,
        "操作": 2.0,
        "場合": 1.5,
        "理由": 2.5,  # 理解を深める観点（中級で重要）
        "なぜ": 2.0,  # 理由を問う
        "適用": 2.0,  # 適用場面
        "背景": 1.5,  # 背景情報
        "する": 1.0,  # 動詞（実務的な内容）
    },
    "advanced": {
        "例外": 3.5,
        "禁止": 3.5,
        "注意": 3.0,
        "判断": 3.0,
        "条件": 2.5,
        "リスク": 2.5,
        "判断基準": 3.0,  # 理解を深める観点（上級で重要）
        "例外ケース": 3.0,  # 例外の理解
        "複合": 2.0,  # 複合的な理解
        "考慮": 2.0,  # 考慮事項
        "罰則": 2.0,
        "してはいけない": 3.0,
        "禁止事項": 3.0,
    },
}

# 見出しパターン（Markdown, PDF見出し）
HEADING_PATTERN = re.compile(r"^(#+\s|第.+章|第.+節|■|●|◆)")

# 最適な長さ（文字数）
OPTIMAL_MIN_LEN = 200
OPTIMAL_MAX_LEN = 800


def score_chunk(text: str, level: str) -> float:
    """
    chunk text を level に応じてスコアリング
    
    Args:
        text: chunk テキスト
        level: 難易度 (beginner / intermediate / advanced)
        
    Returns:
        スコア（高いほど出題に向く）
    """
    # NFC正規化（macOS NFD対策）
    text_norm = unicodedata.normalize("NFC", text)
    
    # 基本スコア
    score = 0.0
    
    # 1. level別キーワードの重み
    keywords = LEVEL_KEYWORDS.get(level, LEVEL_KEYWORDS["beginner"])
    for keyword, weight in keywords.items():
        # キーワード出現回数 × 重み（ただし最大3回まで）
        count = min(text_norm.count(keyword), 3)
        score += count * weight
    
    # 2. 見出しボーナス（行頭が見出しパターン）
    if HEADING_PATTERN.match(text_norm):
        score += 2.0
    
    # 3. 長さボーナス（200〜800文字が最適）
    text_len = len(text_norm)
    if OPTIMAL_MIN_LEN <= text_len <= OPTIMAL_MAX_LEN:
        # 最適範囲内: +2.0
        score += 2.0
    elif text_len < OPTIMAL_MIN_LEN:
        # 短すぎ: 減点（ただし極端には減点しない）
        score -= (OPTIMAL_MIN_LEN - text_len) / 100.0
    else:
        # 長すぎ: 減点（ただし極端には減点しない）
        score -= (text_len - OPTIMAL_MAX_LEN) / 200.0
    
    # 4. 質問形式が含まれる場合は減点（Quiz生成には不向き）
    if "?" in text_norm or "？" in text_norm:
        score -= 1.0
    
    return score


def select_chunks(
    chunks: List[Dict],
    level: str,
    top_n: int
) -> List[Dict]:
    """
    level に応じて出題に向く chunk を選択
    
    Args:
        chunks: chunk リスト（各chunkは {"id": str, "document": str, "metadata": dict} の形式）
        level: 難易度 (beginner / intermediate / advanced)
        top_n: 選択する件数
        
    Returns:
        選択された chunk リスト（スコア降順）
    """
    # 各chunkをスコアリング
    scored_chunks: List[Tuple[float, Dict]] = []
    
    for chunk in chunks:
        text = chunk.get("document", "")
        score = score_chunk(text, level)
        scored_chunks.append((score, chunk))
    
    # スコア降順でソート
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    
    # 上位 top_n 件を返す
    selected = [chunk for score, chunk in scored_chunks[:top_n]]
    
    # デバッグログ
    if len(scored_chunks) > 0:
        top_scores = [round(score, 2) for score, _ in scored_chunks[:min(5, len(scored_chunks))]]
        logger.info(f"[ChunkSelector] {level} で {len(chunks)}件から{len(selected)}件選択, top_scores={top_scores}")
    
    return selected
