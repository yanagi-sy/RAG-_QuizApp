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
    total_text_len = 0
    empty_pages = 0
    
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text()
            text_len = len(text.strip()) if text else 0

            # NEW: ページごとのテキスト長を記録
            if text_len == 0:
                empty_pages += 1
                continue

            total_text_len += text_len
            documents.append(
                Document(
                    source=file_path.name,
                    page=page_num + 1,  # 1始まり
                    text=text,
                )
            )
        doc.close()
        
        # NEW: PDF読み込み結果をログ出力（抽出テキスト長、ページ数）
        if total_text_len == 0:
            logger.warning(
                f"PDFからテキストが抽出できませんでした（画像PDFの可能性）: {file_path.name} "
                f"(全{total_pages}ページ、抽出テキスト=0文字)"
            )
        elif empty_pages > 0:
            logger.info(
                f"PDF読み込み: {file_path.name} - "
                f"抽出成功: {len(documents)}ページ/{total_pages}ページ, "
                f"テキスト合計: {total_text_len}文字, "
                f"空ページ: {empty_pages}ページ（スキャン画像の可能性）"
            )
        else:
            logger.info(
                f"PDF読み込み: {file_path.name} - "
                f"{len(documents)}ページ, テキスト合計: {total_text_len}文字"
            )
            
    except Exception as e:
        # PDF読み込みエラーはログに記録してスキップ
        logger.warning(f"PDF読み込みエラー（スキップ）: {file_path.name} - {type(e).__name__}: {str(e)}")
        return documents

    return documents


def _find_repo_root() -> Path:
    """
    リポジトリルートを取得する（backend/app/docs/loader.py から4階層上）
    
    Returns:
        リポジトリルートのPathオブジェクト（絶対パス）
    """
    # CHANGED: 現在のファイル（backend/app/docs/loader.py）から4階層上でrepo_root
    # loader.py -> docs/ -> app/ -> backend/ -> repo_root
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent.parent.parent
    
    # 検証: backend/ディレクトリが存在するか確認
    backend_dir = repo_root / "backend"
    if not backend_dir.exists() or not backend_dir.is_dir():
        # フォールバック: parentsを辿ってbackend/を探す
        for parent in current_file.parents:
            backend_check = parent / "backend"
            if backend_check.exists() and backend_check.is_dir():
                repo_root = parent
                break
    
    return repo_root.resolve()  # CHANGED: 絶対パスで返す


def load_documents(docs_dir: str) -> List[Document]:
    """
    manualsディレクトリ配下のドキュメントを読み込む

    Args:
        docs_dir: ドキュメントディレクトリパス（リポジトリルートからの相対パス）

    Returns:
        Documentのリスト
    """
    documents = []
    
    # CHANGED: リポジトリルートを取得し、docs_dirを絶対パスに解決
    repo_root = _find_repo_root()
    docs_path = (repo_root / docs_dir).resolve()
    
    # NEW: docs_absパスをログ出力（観測性強化）
    logger.info(f"DOCS_DIR実パス: {docs_path} (exists={docs_path.exists()})")

    if not docs_path.exists():
        logger.warning(f"ドキュメントディレクトリが存在しません: {docs_path}")
        return documents
    
    # NEW: 読み込むファイル一覧をログ出力（最低ファイル名数）
    txt_files = list(docs_path.glob("*.txt"))
    pdf_files = list(docs_path.glob("*.pdf"))
    file_names = [f.name for f in txt_files + pdf_files]
    # ファイル数が多い場合は先頭5件だけ表示
    if len(file_names) > 5:
        file_names_display = file_names[:5] + [f"... (他{len(file_names) - 5}件)"]
    else:
        file_names_display = file_names
    logger.info(f"読み込み対象ファイル: {len(file_names)}件 - {file_names_display}")

    # .txt ファイルを読み込む
    loaded_txt_files = []
    loaded_pdf_files = []
    txt_doc_count = 0
    pdf_doc_count = 0
    
    for txt_file in docs_path.glob("*.txt"):
        try:
            doc = load_txt_file(txt_file)
            documents.append(doc)
            loaded_txt_files.append(txt_file.name)
            txt_doc_count += 1
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
                loaded_pdf_files.append(pdf_file.name)
                pdf_doc_count += len(pdf_docs)
        except Exception as e:
            # 予期しないエラーはログに記録
            logger.error(f"PDF処理中にエラーが発生しました（スキップ）: {pdf_file.name} - {type(e).__name__}: {str(e)}")
            continue
    
    # NEW: 読み込み完了ファイル数（txt/pdf別）をログ出力
    logger.info(
        f"ドキュメント読み込み完了: "
        f"TXT={len(loaded_txt_files)}ファイル({txt_doc_count}ドキュメント), "
        f"PDF={len(loaded_pdf_files)}ファイル({pdf_doc_count}ドキュメント), "
        f"合計={len(documents)}ドキュメント"
    )
    if loaded_txt_files:
        logger.info(f"読み込み成功TXTファイル: {loaded_txt_files}")
    if loaded_pdf_files:
        logger.info(f"読み込み成功PDFファイル: {loaded_pdf_files}")

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
