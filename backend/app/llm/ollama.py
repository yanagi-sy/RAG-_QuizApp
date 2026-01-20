"""
Ollama LLMクライアント実装
"""
import logging
from functools import lru_cache
from typing import List, Dict, Any, Tuple

import httpx

from app.core.settings import settings
from app.llm.base import LLMClient, LLMTimeoutError, LLMInternalError

# ロガー設定
logger = logging.getLogger(__name__)


def extract_ollama_text(raw: Any) -> Tuple[str, dict]:
    """
    Ollama APIレスポンスからテキストを抽出（複数形式対応）
    
    対応形式:
    - dict["message"]["content"]（chat API）
    - dict["response"]（generate API）
    - dict["text"] / dict["content"]（保険）
    - list（streaming、再帰的に連結）
    - str（そのまま返す）
    - その他（str変換）
    
    Args:
        raw: Ollama APIからの生レスポンス
        
    Returns:
        (抽出されたテキスト, デバッグ情報)
    """
    debug_info = {
        "ollama_raw_type": type(raw).__name__,
        "ollama_raw_keys": None,
    }
    
    # Noneの場合
    if raw is None:
        return "", debug_info
    
    # strの場合（既に抽出済み）
    if isinstance(raw, str):
        return raw, debug_info
    
    # dictの場合（chat API / generate API）
    if isinstance(raw, dict):
        debug_info["ollama_raw_keys"] = list(raw.keys())
        
        # chat API形式: {"message": {"content": "..."}}
        if "message" in raw and isinstance(raw["message"], dict):
            content = raw["message"].get("content", "")
            if content:
                return str(content), debug_info
        
        # generate API形式: {"response": "..."}
        if "response" in raw:
            response = raw["response"]
            if response:
                return str(response), debug_info
        
        # 保険: {"text": "..."}
        if "text" in raw:
            text = raw["text"]
            if text:
                return str(text), debug_info
        
        # 保険: {"content": "..."}
        if "content" in raw:
            content = raw["content"]
            if content:
                return str(content), debug_info
        
        # どのキーも見つからない場合は空文字
        logger.warning(f"Ollamaレスポンスから抽出できませんでした: keys={list(raw.keys())}")
        return "", debug_info
    
    # listの場合（streaming形式、再帰的に連結）
    if isinstance(raw, list):
        parts = []
        for item in raw:
            text, _ = extract_ollama_text(item)
            if text:
                parts.append(text)
        return "".join(parts), debug_info
    
    # その他の型（int, float等）はstr変換
    try:
        return str(raw), debug_info
    except Exception as e:
        logger.error(f"Ollama生レスポンスのstr変換に失敗: {type(raw).__name__}: {e}")
        return "", debug_info


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
    
    async def chat(self, messages: List[Dict[str, str]], is_quiz: bool = False) -> str:
        """
        チャット形式でOllamaに問い合わせ、回答を取得
        
        Args:
            messages: メッセージリスト（[{"role": "system", "content": "..."}, ...]）
            is_quiz: Quiz生成モード（JSON強制、生成上限適用）
            
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
        
        # Quiz専用最適化（JSON安定性と速度改善）
        if is_quiz:
            # Quiz専用モデルがあれば上書き
            if settings.quiz_ollama_model:
                payload["model"] = settings.quiz_ollama_model
            
            # format: json を強制（JSON安定性向上）
            if settings.quiz_force_json:
                payload["format"] = "json"
            
            # options: 生成上限、コンテキスト上限、temperature
            payload["options"] = {
                "num_predict": settings.quiz_ollama_num_predict,
                "num_ctx": settings.quiz_ollama_num_ctx,
                "temperature": settings.quiz_ollama_temperature,
            }
            
            logger.info(
                f"Quiz専用モード: model={payload['model']}, "
                f"num_predict={settings.quiz_ollama_num_predict}, "
                f"num_ctx={settings.quiz_ollama_num_ctx}, "
                f"temperature={settings.quiz_ollama_temperature}, "
                f"force_json={settings.quiz_force_json}"
            )
        
        try:
            # httpx.AsyncClient でリクエスト送信
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(self.chat_url, json=payload)
                response.raise_for_status()  # HTTPエラーを例外に変換
                
                # レスポンスから回答を抽出（堅牢化版）
                result = response.json()
                
                # extract_ollama_text で複数形式に対応
                answer, debug_info = extract_ollama_text(result)
                
                # デバッグログ（Quiz専用）
                if is_quiz:
                    logger.info(
                        f"Ollama生レスポンス: type={debug_info['ollama_raw_type']}, "
                        f"keys={debug_info['ollama_raw_keys']}, "
                        f"extracted_chars={len(answer)}"
                    )
                
                # 空応答チェック（Quiz専用）
                if is_quiz and not answer.strip():
                    logger.error(f"Ollamaが空応答を返しました: debug_info={debug_info}")
                    raise LLMInternalError("empty_response")
                
                logger.info(f"Ollama回答取得成功: {len(answer)}文字")
                return answer
        
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
