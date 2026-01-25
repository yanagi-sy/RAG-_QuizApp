"""
ドキュメント関連の型定義（データの形を明示）

【初心者向け】
- dataclass: フィールドだけ持つ軽量なクラス。JSONやDBとのやりとりでよく使う
- Document = 1ファイル（または1ページ）分の生テキスト
- DocumentChunk = チャンク分割後の1ブロック。検索・Embeddingの最小単位
"""
from dataclasses import dataclass


@dataclass
class Document:
    """ドキュメント（1ファイル or 1ページ単位）"""
    source: str   # ファイル名（例: sample.txt）
    page: int     # PDFならページ番号、txtは1固定
    text: str     # 抽出した生テキスト


@dataclass
class DocumentChunk:
    """ドキュメントチャンク（分割後の1塊）"""
    source: str       # ファイル名
    page: int         # ページ番号
    chunk_index: int  # そのファイル内でのチャンク番号（0始まり）
    text: str         # チャンクのテキスト
