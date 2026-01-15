"""
ドキュメント読み込みモジュール
"""
import logging
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from app.docs.models import Document

# ロガー設定
logger = logging.getLogger(__name__)


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
    except Exception as e:
        # PDF読み込みエラーはログに記録してスキップ
        logger.warning(f"PDF読み込みエラー（スキップ）: {file_path.name} - {type(e).__name__}: {str(e)}")
        return documents

    return documents


def _find_repo_root() -> Path:
    """
    リポジトリルートを取得する

    Returns:
        リポジトリルートのPathオブジェクト
    """
    # 現在のファイル（backend/app/docs/loader.py）の絶対パスから開始
    current_file = Path(__file__).resolve()
    
    # 親ディレクトリを辿ってリポジトリルートを探す
    # リポジトリルートの目印: backend/ ディレクトリが存在する
    for parent in current_file.parents:
        backend_dir = parent / "backend"
        if backend_dir.exists() and backend_dir.is_dir():
            # backend/ の親がリポジトリルート
            return parent
    
    # 見つからない場合は、従来の方法（4階層上）をフォールバック
    return current_file.parent.parent.parent.parent


def load_documents(docs_dir: str) -> List[Document]:
    """
    manualsディレクトリ配下のドキュメントを読み込む

    Args:
        docs_dir: ドキュメントディレクトリパス（リポジトリルートからの相対パス）

    Returns:
        Documentのリスト
    """
    documents = []
    
    # リポジトリルートを取得
    repo_root = _find_repo_root()
    docs_path = repo_root / docs_dir

    if not docs_path.exists():
        logger.warning(f"ドキュメントディレクトリが存在しません: {docs_path}")
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
            if len(pdf_docs) == 0:
                # テキストが抽出できなかったPDF（スキャン画像など）
                logger.warning(f"PDFからテキストが抽出できませんでした（スキップ）: {pdf_file.name}")
            else:
                documents.extend(pdf_docs)
        except Exception as e:
            # 予期しないエラーはログに記録
            logger.error(f"PDF処理中にエラーが発生しました（スキップ）: {pdf_file.name} - {type(e).__name__}: {str(e)}")
            continue

    return documents


def load_documents_by_file(docs_dir: str) -> dict[str, List[Document]]:
    """
    ファイル単位でドキュメントを読み込む（ファイル名をキーとした辞書）

    Args:
        docs_dir: ドキュメントディレクトリパス（リポジトリルートからの相対パス）

    Returns:
        ファイル名をキーとしたDocumentリストの辞書
    """
    files_dict: dict[str, List[Document]] = {}
    
    # リポジトリルートを取得
    repo_root = _find_repo_root()
    docs_path = repo_root / docs_dir

    if not docs_path.exists():
        logger.warning(f"ドキュメントディレクトリが存在しません: {docs_path}")
        return files_dict

    # .txt ファイルを読み込む
    for txt_file in docs_path.glob("*.txt"):
        try:
            doc = load_txt_file(txt_file)
            files_dict[txt_file.name] = [doc]
        except Exception:
            # 読み込みエラーは無視
            continue

    # .pdf ファイルを読み込む
    for pdf_file in docs_path.glob("*.pdf"):
        try:
            pdf_docs = load_pdf_file(pdf_file)
            if len(pdf_docs) == 0:
                # テキストが抽出できなかったPDF（スキャン画像など）
                logger.warning(f"PDFからテキストが抽出できませんでした（スキップ）: {pdf_file.name}")
            else:
                files_dict[pdf_file.name] = pdf_docs
        except Exception as e:
            # 予期しないエラーはログに記録
            logger.error(f"PDF処理中にエラーが発生しました（スキップ）: {pdf_file.name} - {type(e).__name__}: {str(e)}")
            continue

    return files_dict
