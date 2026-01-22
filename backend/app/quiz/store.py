"""
Quiz用ストア（in-memory + JSONファイルベース永続化）

QuizItem: in-memoryストア（旧実装、後方互換性のため維持）
QuizSet: JSONファイルベース永続化（新実装）
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.schemas.common import Citation

# ロガー設定
logger = logging.getLogger(__name__)


@dataclass
class QuizItem:
    """クイズアイテム"""
    question: str
    correct_answer: bool
    explanation: str
    citations: list[Citation]


# in-memoryストア（キー：quiz_id、値：QuizItem）
_quiz_store: dict[str, QuizItem] = {}


def save_quiz(item: QuizItem) -> str:
    """
    クイズを保存してquiz_idを返す
    
    Args:
        item: クイズアイテム
        
    Returns:
        quiz_id: UUID文字列
    """
    quiz_id = str(uuid.uuid4())
    _quiz_store[quiz_id] = item
    return quiz_id


def get_quiz(quiz_id: str) -> Optional[QuizItem]:
    """
    クイズを取得する
    
    Args:
        quiz_id: クイズID
        
    Returns:
        QuizItem または None
    """
    return _quiz_store.get(quiz_id)


def clear_all() -> None:
    """すべてのクイズをクリアする（テスト用）"""
    _quiz_store.clear()


# --- QuizSet永続化（JSONファイルベース） ---

def _get_store_dir() -> Path:
    """
    ストアディレクトリのパスを取得（存在しない場合は作成）
    
    Returns:
        Path: ストアディレクトリのパス
    """
    # リポジトリルートを特定（backend/app/quiz/store.py から見て ../../..）
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent.parent.parent
    store_dir = repo_root / "backend" / "data" / "quiz_sets"
    
    # ディレクトリが存在しない場合は作成
    store_dir.mkdir(parents=True, exist_ok=True)
    
    return store_dir


def save_quiz_set(payload: Dict[str, Any]) -> str:
    """
    クイズセットをJSONファイルとして保存
    
    Args:
        payload: クイズセットデータ（quizzes, source_ids, level, count, debug含む）
        
    Returns:
        str: セットID（新規生成）
    """
    store_dir = _get_store_dir()
    
    # IDを新規生成
    set_id = str(uuid.uuid4())
    
    # タイトルを生成
    level_text = {
        "beginner": "初級",
        "intermediate": "中級",
        "advanced": "上級",
    }.get(payload.get("level", "beginner"), "初級")
    
    title = f"Quiz Set ({level_text})"
    
    # セットデータを作成
    quiz_set_data = {
        "id": set_id,
        "title": title,
        "difficulty": payload.get("level", "beginner"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "quizzes": payload.get("quizzes", []),
    }
    
    # JSONファイルとして保存
    file_path = store_dir / f"{set_id}.json"
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(quiz_set_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"QuizSet saved: {set_id} -> {file_path}")
        return set_id
        
    except Exception as e:
        logger.error(f"Failed to save quiz set {set_id}: {e}")
        raise


def load_quiz_set(set_id: str) -> Optional[Dict[str, Any]]:
    """
    クイズセットをJSONファイルから読み込み
    
    Args:
        set_id: セットID
        
    Returns:
        Dict[str, Any]: クイズセットデータ、またはNone（見つからない場合）
    """
    store_dir = _get_store_dir()
    file_path = store_dir / f"{set_id}.json"
    
    if not file_path.exists():
        logger.warning(f"QuizSet not found: {set_id}")
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        logger.debug(f"QuizSet loaded: {set_id}")
        return data
        
    except Exception as e:
        logger.error(f"Failed to load quiz set {set_id}: {e}")
        raise


def list_quiz_sets(
    level: Optional[str] = None,
    source_ids: Optional[List[str]] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    クイズセットの一覧を取得（メタデータのみ）
    
    Args:
        level: 難易度でフィルタ（None=全て）
        source_ids: ソースIDでフィルタ（None=全て、現状は未実装）
        limit: 取得件数上限
        
    Returns:
        List[Dict[str, Any]]: メタデータリスト（id, title, difficulty, created_at, question_count）
    """
    store_dir = _get_store_dir()
    
    if not store_dir.exists():
        return []
    
    metadata_list = []
    
    # 全JSONファイルを読み込み
    for file_path in store_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 難易度フィルタ
            if level and data.get("difficulty") != level:
                continue
            
            # メタデータを抽出
            metadata = {
                "id": data.get("id", file_path.stem),
                "title": data.get("title", f"Quiz Set {data.get('id', 'unknown')}"),
                "difficulty": data.get("difficulty", "unknown"),
                "created_at": data.get("created_at", ""),
                "question_count": len(data.get("quizzes", []))
            }
            
            metadata_list.append(metadata)
            
        except Exception as e:
            logger.warning(f"Failed to load quiz set from {file_path}: {e}")
            continue
    
    # created_atでソート（新しい順）
    metadata_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # 件数制限
    return metadata_list[:limit]


def delete_quiz_set(set_id: str) -> bool:
    """
    クイズセットを削除
    
    Args:
        set_id: セットID
        
    Returns:
        bool: 削除成功時True、見つからない場合False
    """
    store_dir = _get_store_dir()
    file_path = store_dir / f"{set_id}.json"
    
    if not file_path.exists():
        logger.warning(f"QuizSet not found for deletion: {set_id}")
        return False
    
    try:
        file_path.unlink()
        logger.info(f"QuizSet deleted: {set_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete quiz set {set_id}: {e}")
        raise
