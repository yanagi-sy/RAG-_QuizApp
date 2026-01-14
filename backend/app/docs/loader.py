"""
ドキュメント読み込みモジュール
"""
import os
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from app.docs.models import Document


def load_txt_file(file_path: Path) -> Document:
    """
    TXTファイルを読み込む

    Args:
        file_path: ファイルパス

    Returns:
        Document
    """
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    return Document(
        source=file_path.name,
        page=1,
        text=text,
    )


def load_pdf_file(file_path: Path) -> List[Document]:
    """
    PDFファイルを読み込む（テキスト抽出可能なもののみ）

    Args:
        file_path: ファイルパス

    Returns:
        Documentのリスト（ページ単位）
    """
    documents = []
    try:
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            # テキストが抽出できない（スキャン画像）場合はスキップ
            if not text or len(text.strip()) == 0:
                continue

            documents.append(
                Document(
                    source=file_path.name,
                    page=page_num + 1,  # 1始まり
                    text=text,
                )
            )
        doc.close()
    except Exception:
        # PDF読み込みエラーは無視（スキップ）
        pass

    return documents


def load_documents(docs_dir: str) -> List[Document]:
    """
    docsディレクトリ配下のドキュメントを読み込む

    Args:
        docs_dir: ドキュメントディレクトリパス

    Returns:
        Documentのリスト
    """
    documents = []
    docs_path = Path(docs_dir)

    if not docs_path.exists():
        return documents

    # .txt ファイルを読み込む
    for txt_file in docs_path.glob("*.txt"):
        try:
            doc = load_txt_file(txt_file)
            documents.append(doc)
        except Exception:
            # 読み込みエラーは無視
            continue

    # .pdf ファイルを読み込む
    for pdf_file in docs_path.glob("*.pdf"):
        try:
            pdf_docs = load_pdf_file(pdf_file)
            documents.extend(pdf_docs)
        except Exception:
            # 読み込みエラーは無視
            continue

    return documents
