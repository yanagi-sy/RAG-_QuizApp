"""
LLMアダプタ層の基底定義（抽象インターフェース・例外）

【初心者向け】
- LLMClient: Protocol。Ollama 等の実装が chat(messages) を提供する約束
- LLMTimeoutError / LLMInternalError: LLM 呼び出し失敗時に raise。routers 等で捕捉
"""
from typing import Protocol, List, Dict, Any


class LLMClient(Protocol):
    """
    LLMクライアントのインターフェース
    
    各LLM実装（Ollama、Gemini等）はこのProtocolに準拠する
    """
    
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        チャット形式でLLMに問い合わせ、回答を取得
        
        Args:
            messages: メッセージリスト（[{"role": "system", "content": "..."}, ...]）
            
        Returns:
            LLMからの回答テキスト
            
        Raises:
            LLMTimeoutError: タイムアウト時
            LLMInternalError: その他のエラー時
        """
        ...


class LLMError(Exception):
    """LLM関連の基底例外"""
    pass


class LLMTimeoutError(LLMError):
    """LLM呼び出しのタイムアウトエラー"""
    pass


class LLMInternalError(LLMError):
    """LLM呼び出しの内部エラー（HTTPエラー、パースエラー等）"""
    pass
