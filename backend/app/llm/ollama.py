"""
Ollama LLMクライアント実装
"""
import logging
from functools import lru_cache
from typing import List, Dict, Any

import httpx

from app.core.settings import settings
from app.llm.base import LLMClient, LLMTimeoutError, LLMInternalError

# ロガー設定
logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Ollama APIクライアント
    
    - httpx.AsyncClient で /api/chat を叩く
    - stream=False の一括応答
    """
    
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: int | None = None,
    ):
        """
        Ollamaクライアントを初期化
        
        Args:
            base_url: OllamaのベースURL（デフォルト: settingsから取得）
            model: 使用するモデル名（デフォルト: settingsから取得）
            timeout_sec: タイムアウト秒数（デフォルト: settingsから取得）
        """
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.timeout_sec = timeout_sec or settings.ollama_timeout_sec
        
        # APIエンドポイント
        self.chat_url = f"{self.base_url}/api/chat"
    
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        チャット形式でOllamaに問い合わせ、回答を取得
        
        Args:
            messages: メッセージリスト（[{"role": "system", "content": "..."}, ...]）
            
        Returns:
            Ollamaからの回答テキスト
            
        Raises:
            LLMTimeoutError: タイムアウト時
            LLMInternalError: HTTPエラーやその他のエラー時
        """
        # リクエストボディを構築
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        
        try:
            # httpx.AsyncClient でリクエスト送信
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(self.chat_url, json=payload)
                response.raise_for_status()  # HTTPエラーを例外に変換
                
                # レスポンスから回答を抽出
                result = response.json()
                
                # Ollamaのレスポンス形式: {"message": {"role": "assistant", "content": "..."}}
                if "message" in result and "content" in result["message"]:
                    answer = result["message"]["content"]
                    logger.info(f"Ollama回答取得成功: {len(answer)}文字")
                    return answer
                else:
                    logger.error(f"Ollamaレスポンス形式が不正: {result}")
                    raise LLMInternalError("Ollamaからのレスポンス形式が不正です")
        
        except httpx.TimeoutException as e:
            logger.error(f"Ollamaタイムアウト: {e}")
            raise LLMTimeoutError(f"Ollamaへのリクエストがタイムアウトしました（{self.timeout_sec}秒）")
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTPエラー: {e.response.status_code} - {e.response.text}")
            raise LLMInternalError(f"Ollama APIエラー: HTTP {e.response.status_code}")
        
        except httpx.RequestError as e:
            logger.error(f"Ollama接続エラー: {e}")
            raise LLMInternalError(f"Ollamaへの接続に失敗しました: {str(e)}")
        
        except Exception as e:
            logger.error(f"Ollama予期しないエラー: {type(e).__name__}: {e}")
            raise LLMInternalError(f"Ollama呼び出し中にエラーが発生しました: {str(e)}")


@lru_cache(maxsize=1)
def get_ollama_client() -> OllamaClient:
    """
    Ollamaクライアントのシングルトンインスタンスを取得（@lru_cacheで生成を抑える）
    
    Returns:
        OllamaClientインスタンス
    """
    return OllamaClient()
