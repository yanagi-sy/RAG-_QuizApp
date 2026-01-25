"""
Quiz API用スキーマ（クイズ生成・セットの型）

【初心者向け】
- QuizGenerateRequest: level, count, source_ids, topic, debug, save
- QuizItem: 1問分（id, type, statement, answer_bool, explanation, citations）
- QuizSet / QuizSetMetadata: 保存したクイズセットとその一覧用
"""
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.schemas.common import Citation

Level = Literal["beginner", "intermediate", "advanced"]
QuizType = Literal["mcq", "true_false"]


class QuizRequest(BaseModel):
    """クイズ出題リクエスト"""
    level: Level = Field(..., description="難易度")


class QuizResponse(BaseModel):
    """クイズ出題レスポンス"""
    quiz_id: str
    question: str


# --- Quiz Generate用スキーマ ---

class RetrievalParams(BaseModel):
    """検索方法パラメータ（/askと同じ）"""
    semantic_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="意味検索の重み（0.0-1.0）。keyword_weight = 1 - semantic_weight"
    )


class QuizGenerateRequest(BaseModel):
    """クイズ生成リクエスト（MVP: 最大3問固定）"""
    level: Level = Field(..., description="難易度")
    count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="生成するクイズの数（1-10）"
    )
    topic: Optional[str] = Field(
        None,
        description="クイズのトピック（例：防災、清掃、決済）"
    )
    source_ids: Optional[list[str]] = Field(
        None,
        description="検索対象の資料ID（例：['security-001', 'ops-001']）。未指定なら全資料対象"
    )
    retrieval: Optional[RetrievalParams] = Field(
        None,
        description="検索方法のパラメータ"
    )
    debug: bool = Field(
        default=False,
        description="デバッグ情報を返すかどうか"
    )
    save: bool = Field(
        default=False,
        description="クイズセットを保存するかどうか"
    )


class QuizItem(BaseModel):
    """生成されたクイズアイテム（○×問題専用）"""
    id: str = Field(..., description="クイズのID（UUID or short id）")
    statement: str = Field(..., description="断言文（疑問形禁止、?/?を含めない）")
    type: QuizType = Field(default="true_false", description="問題タイプ（true_false固定）")
    answer_bool: bool = Field(..., description="正解（true=○、false=×）")
    explanation: str = Field(..., description="根拠の引用に基づく解説")
    citations: list[Citation] = Field(..., description="引用元のリスト（1件以上必須）")
    
    # フロント互換性のため question も提供（statement のエイリアス）
    @property
    def question(self) -> str:
        """互換性のため question プロパティを提供"""
        return self.statement


class QuizGenerateResponse(BaseModel):
    """クイズ生成レスポンス"""
    quizzes: list[QuizItem] = Field(..., description="生成されたクイズのリスト")
    quiz_set_id: Optional[str] = Field(
        None,
        description="保存されたクイズセットID（save=trueの場合のみ）"
    )
    debug: Optional[Dict[str, Any]] = Field(
        None,
        description="デバッグ情報（debug=trueの場合のみ）"
    )


class QuizSetMetadata(BaseModel):
    """クイズセットメタデータ（一覧用）"""
    id: str = Field(..., description="セットID")
    title: str = Field(..., description="セットタイトル")
    difficulty: Level = Field(..., description="難易度")
    created_at: str = Field(..., description="作成日時（ISO形式）")
    question_count: int = Field(..., description="問題数")


class QuizSet(BaseModel):
    """クイズセット"""
    id: str = Field(..., description="セットID")
    title: str = Field(..., description="セットタイトル")
    difficulty: Level = Field(..., description="難易度")
    created_at: str = Field(..., description="作成日時（ISO形式）")
    quizzes: list[QuizItem] = Field(..., description="問題リスト")


class QuizSetListResponse(BaseModel):
    """クイズセット一覧レスポンス"""
    quiz_sets: list[QuizSetMetadata] = Field(..., description="セットメタデータリスト")
    total: int = Field(..., description="総件数")
