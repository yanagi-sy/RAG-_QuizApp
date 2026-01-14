"""
アプリケーション設定
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """アプリケーション設定"""

    # CORS設定
    cors_origins: List[str] = ["http://localhost:3000"]

    # ドキュメントディレクトリ
    docs_dir: str = "docs"

    # 将来のGEMINI APIキー（未使用）
    # gemini_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# グローバル設定インスタンス
settings = Settings()
