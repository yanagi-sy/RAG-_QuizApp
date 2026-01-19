"""
アプリケーション設定
"""
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """アプリケーション設定"""

    # CORS設定
    cors_origins: List[str] = ["http://localhost:3000"]

    # ドキュメントディレクトリ（リポジトリルートからの相対パス）
    docs_dir: str = "manuals"

    # RAG設定（Semantic Retrieval用）  # NEW
    chroma_dir: str = Field(
        default="backend/.chroma",  # CHANGED: デフォルトをbackend/.chromaに固定
        alias="CHROMA_DIR",
        description="ChromaDBの永続化ディレクトリ"
    )
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-small",
        alias="EMBEDDING_MODEL",
        description="Embeddingモデル名"
    )
    chunk_size: int = Field(
        default=800,
        alias="CHUNK_SIZE",
        description="チャンクサイズ（文字数）"
    )
    chunk_overlap: int = Field(
        default=120,
        alias="CHUNK_OVERLAP",
        description="チャンクオーバーラップ（文字数）"
    )
    top_k: int = Field(
        default=5,
        alias="TOP_K",
        description="Semantic検索の取得件数"
    )
    keyword_min_score: int = Field(
        default=2,
        alias="KEYWORD_MIN_SCORE",
        description="キーワード検索の最小スコア閾値（ノイズ除去用）"
    )
    semantic_min_threshold: float = Field(
        default=0.3,
        alias="SEMANTIC_MIN_THRESHOLD",
        description="ハイブリッド検索時の最小semantic score閾値（これ以下はkeywordスコアに関わらず除外）"
    )

    # Ollama設定（環境変数名を明示的に指定して事故防止）
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
        description="Ollama APIのベースURL"
    )
    ollama_model: str = Field(
        default="llama3",
        alias="OLLAMA_MODEL",
        description="使用するOllamaモデル名"
    )
    ollama_timeout_sec: int = Field(
        default=30,
        alias="OLLAMA_TIMEOUT_SEC",
        description="Ollama API呼び出しのタイムアウト秒数"
    )

    # 将来のGEMINI APIキー（未使用）
    # gemini_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        populate_by_name = True  # Fieldのaliasとフィールド名の両方で読み込み可能


# グローバル設定インスタンス
settings = Settings()
