"""
Gemini API LLMクライアント（Google Gemini APIとの通信）

【初心者向け】
- Google Gemini APIを使用してLLMを呼び出す
- OllamaClientと同じLLMClientインターフェースを実装
- これにより、既存のコードを変更せずに切り替え可能
"""
import asyncio
import logging
from functools import lru_cache
from typing import List, Dict, Any

import google.generativeai as genai

from app.core.settings import settings
from app.llm.base import LLMClient, LLMTimeoutError, LLMInternalError

# ロガー設定
logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Gemini APIクライアント
    
    - google.generativeai を使用してGemini APIを呼び出す
    - LLMClientインターフェースに準拠
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_sec: int | None = None,
    ):
        """
        Geminiクライアントを初期化
        
        Args:
            api_key: Gemini APIキー（デフォルト: settingsから取得）
            model: 使用するモデル名（デフォルト: settingsから取得）
            timeout_sec: タイムアウト秒数（デフォルト: settingsから取得）
        """
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model or settings.gemini_model
        self.timeout_sec = timeout_sec or settings.gemini_timeout_sec
        
        # APIキーを設定
        if not self.api_key:
            raise ValueError("Gemini APIキーが設定されていません。GEMINI_API_KEY環境変数を設定してください。")
        
        genai.configure(api_key=self.api_key)
        
        # モデルを取得
        try:
            self.model = genai.GenerativeModel(self.model_name)
        except Exception as e:
            logger.error(f"Geminiモデルの初期化に失敗: {e}")
            raise LLMInternalError(f"Geminiモデルの初期化に失敗しました: {str(e)}")
    
    async def chat(self, messages: List[Dict[str, str]], is_quiz: bool = False) -> str:
        """
        チャット形式でGemini APIに問い合わせ、回答を取得
        
        Args:
            messages: メッセージリスト（[{"role": "system", "content": "..."}, ...]）
            is_quiz: Quiz生成モード（生成パラメータの調整）
            
        Returns:
            Gemini APIからの回答テキスト
            
        Raises:
            LLMTimeoutError: タイムアウト時
            LLMInternalError: APIエラーやその他のエラー時
        """
        try:
            # Gemini APIのメッセージ形式に変換
            # Gemini APIは "user" と "model" のロールのみサポート
            # "system" ロールは最初の "user" メッセージに統合
            gemini_messages = []
            system_content = None
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    # systemメッセージは最初のuserメッセージに統合
                    if system_content is None:
                        system_content = content
                    else:
                        system_content += "\n\n" + content
                elif role == "user":
                    # systemメッセージがある場合は統合
                    if system_content:
                        user_content = f"{system_content}\n\n{content}"
                        system_content = None  # 統合済み
                    else:
                        user_content = content
                    gemini_messages.append({"role": "user", "parts": [user_content]})
                elif role == "assistant":
                    gemini_messages.append({"role": "model", "parts": [content]})
            
            # 最後にsystemメッセージが残っている場合は、最初のuserメッセージに統合
            if system_content and gemini_messages:
                if gemini_messages[0]["role"] == "user":
                    gemini_messages[0]["parts"][0] = f"{system_content}\n\n{gemini_messages[0]['parts'][0]}"
            
            # 生成パラメータを設定
            generation_config = {}
            if is_quiz:
                # Quiz専用モデルがあれば使用
                if settings.quiz_gemini_model:
                    self.model = genai.GenerativeModel(settings.quiz_gemini_model)
                
                # Quiz専用パラメータ
                generation_config = {
                    "max_output_tokens": settings.quiz_gemini_max_output_tokens,
                    "temperature": settings.quiz_gemini_temperature,
                }
                
                logger.info(
                    f"Quiz専用モード: model={self.model_name}, "
                    f"max_output_tokens={settings.quiz_gemini_max_output_tokens}, "
                    f"temperature={settings.quiz_gemini_temperature}"
                )
            
            # Gemini APIを呼び出し
            # 注意: Gemini APIは非同期を直接サポートしていないため、同期呼び出しをasyncioでラップ
            def _generate():
                try:
                    response = self.model.generate_content(
                        gemini_messages,
                        generation_config=generation_config if generation_config else None,
                    )
                    return response.text
                except Exception as e:
                    raise LLMInternalError(f"Gemini API呼び出しエラー: {str(e)}")
            
            # タイムアウト付きで実行
            answer = await asyncio.wait_for(
                asyncio.to_thread(_generate),
                timeout=self.timeout_sec
            )
            
            # 空応答チェック（Quiz専用）
            if is_quiz and not answer.strip():
                logger.error("Gemini APIが空応答を返しました")
                raise LLMInternalError("empty_response")
            
            logger.info(f"Gemini API回答取得成功: {len(answer)}文字")
            return answer
        
        except asyncio.TimeoutError:
            logger.error(f"Gemini APIタイムアウト: {self.timeout_sec}秒")
            raise LLMTimeoutError(f"Gemini APIへのリクエストがタイムアウトしました（{self.timeout_sec}秒）")
        
        except LLMInternalError:
            raise  # 既にLLMInternalErrorの場合はそのまま
        
        except Exception as e:
            logger.error(f"Gemini API予期しないエラー: {type(e).__name__}: {e}")
            raise LLMInternalError(f"Gemini API呼び出し中にエラーが発生しました: {str(e)}")


@lru_cache(maxsize=1)
def get_gemini_client() -> GeminiClient:
    """
    Geminiクライアントのシングルトンインスタンスを取得（@lru_cacheで生成を抑える）
    
    Returns:
        GeminiClientインスタンス
    """
    return GeminiClient()
