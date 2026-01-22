"""
日本語前提のチャンキング（見出し境界優先）

見出し（##, ###）や区切り（---）でセクション分割し、
セクションごとにチャンク化することで、トピック混在を防ぐ。
"""
import re
from typing import List

from app.docs.models import Document, DocumentChunk


def split_into_sections(text: str) -> List[str]:
    """
    テキストをセクションに分割（見出し境界優先）
    
    優先順位:
    1. "\n---\n" で分割（前後空白は吸収）
    2. 見出し境界（^###+ など）で分割
    
    Args:
        text: 元のテキスト
        
    Returns:
        セクションのリスト
    """
    sections = []
    
    # 最優先: "\n---\n" で分割
    parts = re.split(r'\n\s*---\s*\n', text)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 見出し境界でさらに分割
        # 見出しパターン:
        # 1. Markdown形式: 行頭の # で始まる行（##, ### など）
        # 2. 番号付き見出し: 行頭が数字+ピリオド（例: "2. 万引き対応"）
        # 3. 番号付き見出し（括弧付き）: 行頭が数字+ピリオド+数字（例: "2.1 絶対にやってはいけないこと"）
        # 4. 区切り線: "---" のみの行
        heading_patterns = [
            r'^#{1,6}\s+.*$',  # Markdown形式
            r'^\d+\.\s+[^\d]',  # 番号付き見出し（例: "2. 万引き対応"）
            r'^\d+\.\d+\s+',  # 番号付き見出し（例: "2.1 絶対に"）
        ]
        lines = part.split('\n')
        current_section = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # 区切り線チェック
            if re.match(r'^---+$', line_stripped):
                # 区切り線が見つかった場合、現在のセクションを保存
                if current_section:
                    section_text = '\n'.join(current_section).strip()
                    if section_text:
                        sections.append(section_text)
                    current_section = []
                continue
            
            # 見出し行かチェック
            is_heading = False
            heading_level = None  # 見出しの階層レベル（1=トップレベル、2=サブレベル）
            
            for i, pattern in enumerate(heading_patterns):
                if re.match(pattern, line_stripped):
                    is_heading = True
                    # パターン0: Markdown形式（#の数でレベル判定）
                    # ##（レベル2）以下をトップレベルとして扱う（###以降はサブレベル）
                    if i == 0:
                        markdown_level = len(re.match(r'^(#+)', line_stripped).group(1))
                        heading_level = 1 if markdown_level <= 2 else 2  # ##以下はトップレベル、###以降はサブレベル
                    # パターン1: トップレベルの番号付き見出し（例: "2. 万引き対応"）
                    elif i == 1:
                        heading_level = 1
                    # パターン2: サブレベルの番号付き見出し（例: "2.1 絶対に"）
                    elif i == 2:
                        heading_level = 2
                    break
            
            if is_heading:
                # トップレベルの見出し（レベル1）の場合のみ、現在のセクションを保存
                # サブレベルの見出し（レベル2、例: "3.1"）は親セクションに含める
                if heading_level == 1:
                    # トップレベルの見出しが見つかった場合、現在のセクションを保存
                    if current_section:
                        section_text = '\n'.join(current_section).strip()
                        if section_text:
                            sections.append(section_text)
                    current_section = [line]
                else:
                    # サブレベルの見出しは現在のセクションに含める
                    current_section.append(line)
            else:
                current_section.append(line)
        
        # 最後のセクションを追加
        if current_section:
            section_text = '\n'.join(current_section).strip()
            if section_text:
                sections.append(section_text)
    
    # セクションが1つもない場合は全体を1セクションとして返す
    if not sections:
        sections = [text.strip()] if text.strip() else []
    
    return sections


def chunk_text_japanese(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    日本語テキストをチャンクに分割（改行・句点ベース、それでも長い場合は固定長）
    
    Args:
        text: 元のテキスト
        chunk_size: チャンクサイズ（文字数）
        chunk_overlap: オーバーラップ文字数
        
    Returns:
        チャンクテキストのリスト
    """
    chunks = []
    
    # 改行で分割（段落単位）
    paragraphs = text.split('\n')
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # 現在のチャンクに追加した場合の長さを確認
        if current_chunk:
            test_chunk = current_chunk + "\n" + para
        else:
            test_chunk = para
        
        if len(test_chunk) <= chunk_size:
            # チャンクサイズ内なら追加
            if current_chunk:
                current_chunk += "\n" + para
            else:
                current_chunk = para
        else:
            # チャンクサイズを超える場合
            if current_chunk:
                # 現在のチャンクを保存
                chunks.append(current_chunk)
                
                # オーバーラップ分を次のチャンクの先頭に
                if chunk_overlap > 0 and len(current_chunk) >= chunk_overlap:
                    overlap_text = current_chunk[-chunk_overlap:]
                    current_chunk = overlap_text + "\n" + para
                else:
                    current_chunk = para
            else:
                # 現在のチャンクが空で、段落が長すぎる場合は句点で分割
                if len(para) > chunk_size:
                    # 句点（。、！？）で分割
                    sentences = re.split(r'([。！？\n])', para)
                    sentence_chunk = ""
                    
                    for i in range(0, len(sentences), 2):
                        if i + 1 < len(sentences):
                            sentence = sentences[i] + sentences[i + 1]
                        else:
                            sentence = sentences[i]
                        
                        if len(sentence_chunk) + len(sentence) <= chunk_size:
                            sentence_chunk += sentence
                        else:
                            if sentence_chunk:
                                chunks.append(sentence_chunk)
                                # オーバーラップ
                                if chunk_overlap > 0 and len(sentence_chunk) >= chunk_overlap:
                                    current_chunk = sentence_chunk[-chunk_overlap:] + sentence
                                else:
                                    current_chunk = sentence
                                sentence_chunk = ""
                            else:
                                # 1文が長すぎる場合は固定長で分割
                                for j in range(0, len(sentence), chunk_size - chunk_overlap):
                                    chunk_text = sentence[j:j + chunk_size]
                                    if chunk_text.strip():
                                        chunks.append(chunk_text)
                    if sentence_chunk:
                        current_chunk = sentence_chunk
                else:
                    current_chunk = para
    
    # 最後のチャンクを追加
    if current_chunk:
        chunks.append(current_chunk)
    
    # CHANGED: 関数末尾で必ず return chunks（ifブロック内に入れない）
    return chunks


def chunk_document_for_rag(document: Document, chunk_size: int, chunk_overlap: int) -> List[DocumentChunk]:
    """
    ドキュメントをRAG用にチャンクに分割（見出し境界優先）
    
    戦略:
    1. まず split_into_sections でセクション分割
    2. 各セクションに対して chunk_text_japanese を適用
    3. セクション境界をまたがない（トピック混在を防ぐ）
    
    Args:
        document: ドキュメント
        chunk_size: チャンクサイズ（セクション内でのチャンクサイズ）
        chunk_overlap: オーバーラップ文字数（セクション内でのオーバーラップ）
        
    Returns:
        DocumentChunkのリスト
    """
    # セクション分割
    sections = split_into_sections(document.text)
    
    all_chunks = []
    chunk_index = 0
    
    # 各セクションをチャンク化
    for section_text in sections:
        # セクション内でチャンク化（overlapはセクション内のみ）
        section_chunks = chunk_text_japanese(section_text, chunk_size, chunk_overlap)
        
        # DocumentChunkに変換
        for chunk_text in section_chunks:
            all_chunks.append(
                DocumentChunk(
                    source=document.source,
                    page=document.page,
                    chunk_index=chunk_index,
                    text=chunk_text,
                )
            )
            chunk_index += 1
    
    return all_chunks
