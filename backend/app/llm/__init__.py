"""
LLMアダプタ層

【初心者向け】
- LLMClientインターフェースを実装したクライアントを提供
- 設定（LLM_PROVIDER）に応じてOllamaまたはGeminiを選択
"""
from app.core.settings import settings
from app.llm.base import LLMClient
from app.llm.ollama import get_ollama_client
from app.llm.gemini import get_gemini_client


def get_llm_client() -> LLMClient:
    """
    LLMクライアントを取得（設定に応じてOllamaまたはGeminiを選択）
    
    【初心者向け】
    環境変数 LLM_PROVIDER の値に応じて、適切なLLMクライアントを返します。
    - "ollama" → OllamaClient
    - "gemini" → GeminiClient
    
    Returns:
        LLMClientインターフェースを実装したクライアント
        
    Raises:
        ValueError: 無効なプロバイダーが指定された場合
    """
    provider = settings.llm_provider.lower()
    
    if provider == "ollama":
        return get_ollama_client()
    elif provider == "gemini":
        return get_gemini_client()
    else:
        raise ValueError(
            f"無効なLLMプロバイダー: {provider}。"
            f"LLM_PROVIDER環境変数に 'ollama' または 'gemini' を指定してください。"
        )
