"""
スニペット（抜粋）とquote作成
"""
from app.docs.models import DocumentChunk


def create_snippet(text: str, query: str, max_length: int = 120) -> str:
    """
    スニペット（抜粋）を作成する

    Args:
        text: 元のテキスト
        query: 検索クエリ
        max_length: 最大文字数

    Returns:
        スニペット文字列
    """
    text_lower = text.lower()
    query_lower = query.lower()
    
    # クエリが含まれる位置を探す（最初の出現位置）
    query_pos = text_lower.find(query_lower)
    
    if query_pos == -1:
        # クエリが見つからない場合は先頭から
        snippet = text[:max_length].strip()
        if len(text) > max_length:
            snippet = snippet[:max_length - 3] + "..."
    else:
        # クエリの前後を取得（前後40文字ずつ）
        context_length = 40
        start = max(0, query_pos - context_length)
        end = min(len(text), query_pos + len(query) + context_length)
        snippet = text[start:end].strip()
        
        # 先頭が途中なら「...」を付ける
        if start > 0:
            snippet = "..." + snippet
        # 末尾が途中なら「...」を付ける
        if end < len(text):
            snippet = snippet + "..."
    
    # 改行を削除して1行に
    snippet = snippet.replace("\n", " ").replace("\r", " ")
    # 連続する空白を1つに
    while "  " in snippet:
        snippet = snippet.replace("  ", " ")
    
    # 重複した文を削除（同じ文が2回以上続く場合、最初の1回だけ残す）
    words = snippet.split()
    if len(words) > 10:
        # 最初の10単語と次の10単語が同じなら、最初だけ残す
        first_10 = " ".join(words[:10])
        if len(words) >= 20:
            second_10 = " ".join(words[10:20])
            if first_10 == second_10:
                # 重複を検出した場合、最初の部分だけを返す
                snippet = first_10 + "..."
    
    # 最大長を超える場合は切り詰め
    if len(snippet) > max_length:
        snippet = snippet[:max_length - 3] + "..."
    
    return snippet


def create_quote(chunk: DocumentChunk, query: str = "", max_length: int = 240) -> str:
    """
    引用用のquoteを作成する（citations用）

    Args:
        chunk: DocumentChunk
        query: 検索クエリ（クエリ位置を優先する場合に使用）
        max_length: 最大文字数

    Returns:
        quote文字列
    """
    text = chunk.text.strip()
    
    # 改行を空白に置換
    text = text.replace("\n", " ").replace("\r", " ")
    # 連続する空白を1つに
    while "  " in text:
        text = text.replace("  ", " ")
    
    # クエリが指定されている場合は、クエリ位置を優先して抜粋
    if query and len(query) > 0:
        text_lower = text.lower()
        query_lower = query.lower()
        
        # クエリが含まれる位置を探す（最初の出現位置）
        query_pos = text_lower.find(query_lower)
        
        if query_pos != -1:
            # クエリの前後を取得（前後50%ずつ）
            context_length = max_length // 2
            start = max(0, query_pos - context_length)
            end = min(len(text), query_pos + len(query) + context_length)
            quote = text[start:end].strip()
            
            # 先頭が途中なら「…」を付ける
            if start > 0:
                quote = "…" + quote
            # 末尾が途中なら「…」を付ける
            if end < len(text):
                quote = quote + "…"
            
            # 最大長を超える場合は切り詰め
            if len(quote) > max_length:
                quote = quote[:max_length - 1] + "…"
            
            return quote
    
    # クエリが見つからない、または指定されていない場合は先頭から
    if len(text) > max_length:
        text = text[:max_length - 1] + "…"
    
    return text
