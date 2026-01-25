"""
ドキュメントチャンク分割モジュール（長文を検索用の塊に分割）

【初心者向け】
- チャンク = 検索・Embeddingの単位。長すぎると精度が落ちるため適度な大きさに分割
- 見出し（##, ###）の境界を優先して切り、意味のまとまりをなるべく保つ
- カテゴリ（FAQ/一般/技術/長文）ごとに chunk_size / chunk_overlap を変えて調整
"""
from typing import List, Literal, Tuple

from app.docs.models import Document, DocumentChunk

# カテゴリ型
Category = Literal["FAQ", "一般", "技術", "長文"]

# カテゴリごとのチャンク設定（固定）
CATEGORY_SETTINGS: dict[Category, Tuple[int, int]] = {
    "FAQ": (400, 40),      # chunk_size, chunk_overlap
    "一般": (800, 80),
    "技術": (1000, 180),
    "長文": (1300, 250),
}


def categorize_by_length(text_len: int) -> Category:
    """
    文字数からカテゴリを判定する

    Args:
        text_len: テキストの文字数

    Returns:
        カテゴリ
    """
    if text_len < 1200:
        return "FAQ"
    elif text_len < 8000:
        return "一般"
    elif text_len < 20000:
        return "技術"
    else:
        return "長文"


def chunk_document(document: Document, chunk_size: int, chunk_overlap: int) -> List[DocumentChunk]:
    """
    ドキュメントをチャンクに分割する（見出し境界で優先的に切る）
    
    戦略:
    - 見出し（##, ###）が来たら、chunk_sizeに達していなくても強制的に切る
    - overlapは見出しをまたがない（見出しの直前で終了）
    - 見出しがない場合は従来通り固定長で切る

    Args:
        document: ドキュメント
        chunk_size: チャンクサイズ
        chunk_overlap: オーバーラップ文字数

    Returns:
        DocumentChunkのリスト
    """
    import re
    
    text = document.text
    text_len = len(text)

    chunks = []
    start = 0
    chunk_index = 0

    while start < text_len:
        end = start + chunk_size
        
        # chunk_size範囲内に見出し（##, ###）があれば、そこで切る
        chunk_text = text[start:end]
        
        # 見出しパターン（行頭の ## または ###）
        heading_match = re.search(r'\n(##+ )', chunk_text)
        
        if heading_match and heading_match.start() > 0:
            # 見出しが見つかった場合、見出しの直前で切る
            end = start + heading_match.start()
            chunk_text = text[start:end]
        
        # チャンクが空でない場合のみ追加
        if chunk_text.strip():
            chunks.append(
                DocumentChunk(
                    source=document.source,
                    page=document.page,
                    chunk_index=chunk_index,
                    text=chunk_text,
                )
            )
            chunk_index += 1

        # 次のチャンクの開始位置
        if heading_match and heading_match.start() > 0:
            # 見出しで切った場合は、overlapなしで次の見出しから始める
            start = end
        else:
            # 通常の場合はoverlap分戻る
            start = end - chunk_overlap
        
        if start >= text_len:
            break

    return chunks


def chunk_documents(documents: List[Document]) -> List[DocumentChunk]:
    """
    複数のドキュメントをチャンクに分割する（後方互換用）

    Args:
        documents: ドキュメントのリスト

    Returns:
        DocumentChunkのリスト
    """
    all_chunks = []
    for doc in documents:
        # 文字数からカテゴリを判定
        text_len = len(doc.text)
        category = categorize_by_length(text_len)
        chunk_size, chunk_overlap = CATEGORY_SETTINGS[category]
        
        # カテゴリに応じた設定でチャンク化
        chunks = chunk_document(doc, chunk_size, chunk_overlap)
        all_chunks.extend(chunks)
    return all_chunks


def chunk_file_documents(file_documents: List[Document]) -> Tuple[Category, int, int, List[DocumentChunk]]:
    """
    ファイル単位のドキュメント（複数ページを結合済み）をチャンクに分割する

    Args:
        file_documents: 同一ファイルのDocumentリスト（ページ単位）

    Returns:
        (カテゴリ, chunk_size, chunk_overlap, DocumentChunkのリスト)
    """
    # ファイル全体のテキストを結合
    combined_text = "".join(doc.text for doc in file_documents)
    text_len = len(combined_text)
    
    # カテゴリ判定
    category = categorize_by_length(text_len)
    chunk_size, chunk_overlap = CATEGORY_SETTINGS[category]
    
    # 結合したテキストで1つのDocumentとして扱う
    combined_doc = Document(
        source=file_documents[0].source,
        page=1,  # 結合後は1ページとして扱う
        text=combined_text,
    )
    
    # チャンク化
    chunks = chunk_document(combined_doc, chunk_size, chunk_overlap)
    
    return category, chunk_size, chunk_overlap, chunks
