# Gemini API移行手順

**初心者の方へ**  
このドキュメントでは、LLMモデルをOllamaからGemini APIに移行する手順を、ステップバイステップで説明します。

---

## 目次

1. [前提条件](#前提条件)
2. [移行手順の概要](#移行手順の概要)
3. [ステップ1: Gemini APIキーの取得](#ステップ1-gemini-apiキーの取得)
4. [ステップ2: 依存関係の追加](#ステップ2-依存関係の追加)
5. [ステップ3: Gemini APIクライアントの実装](#ステップ3-gemini-apiクライアントの実装)
6. [ステップ4: 設定の追加](#ステップ4-設定の追加)
7. [ステップ5: LLMクライアントファクトリの作成](#ステップ5-llmクライアントファクトリの作成)
8. [ステップ6: 使用箇所の更新](#ステップ6-使用箇所の更新)
9. [ステップ7: 動作確認](#ステップ7-動作確認)
10. [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

- Python 3.11以上
- Google Cloud Platform（GCP）アカウント
- Gemini APIキー（後述の手順で取得）

---

## 移行手順の概要

現在の実装では、`LLMClient`というProtocol（インターフェース）が定義されており、`OllamaClient`がこれを実装しています。  
Gemini APIに移行する場合も、同じ`LLMClient`インターフェースを実装することで、既存のコードを変更せずに切り替えられるようになっています。

**移行の流れ:**
1. Gemini APIクライアントを実装（`LLMClient`インターフェースに準拠）
2. 設定でLLMプロバイダーを選択可能にする
3. 使用箇所を更新（ファクトリ関数を使用）

---

## ステップ1: Gemini APIキーの取得

### 1.1 Google AI Studioにアクセス

1. [Google AI Studio](https://makersuite.google.com/app/apikey) にアクセス
2. Googleアカウントでログイン
3. 「Create API Key」をクリック
4. APIキーをコピー（後で使用します）

### 1.2 環境変数に設定

**`backend/.env`ファイル**に以下を追加：

```env
# Gemini API設定
GEMINI_API_KEY=your_api_key_here
LLM_PROVIDER=gemini  # ollama または gemini
```

**具体的な手順:**
1. `backend/.env`ファイルを開く（テキストエディタで）
2. ファイルの末尾に上記の2行を追加
3. `your_api_key_here`の部分を、ステップ1.1で取得したAPIキーに置き換える
4. ファイルを保存

**例:**
```env
# Gemini API設定
GEMINI_API_KEY=AIzaSyAbc123Xyz789...（実際のAPIキー）
LLM_PROVIDER=gemini
```

**注意**: 
- APIキーは機密情報のため、`.gitignore`に`.env`が含まれていることを確認してください（既に含まれています）
- APIキーをGitにコミットしないよう注意してください
- `backend/.env`ファイルは既に存在しているので、そのファイルに追加してください

---

## ステップ2: 依存関係の追加

`backend/requirements.txt`に以下を追加：

```txt
google-generativeai==0.8.3
```

その後、依存関係をインストール：

```bash
cd backend
pip install -r requirements.txt
```

---

## ステップ3: Gemini APIクライアントの実装

`backend/app/llm/gemini.py`を新規作成：

```python
"""
Gemini API LLMクライアント（Google Gemini APIとの通信）

【初心者向け】
- Google Gemini APIを使用してLLMを呼び出す
- OllamaClientと同じLLMClientインターフェースを実装
- これにより、既存のコードを変更せずに切り替え可能
"""
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
            import asyncio
            
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
```

---

## ステップ4: 設定の追加

`backend/app/core/settings.py`に以下を追加：

```python
    # Gemini API設定
    gemini_api_key: str = Field(
        default="",
        alias="GEMINI_API_KEY",
        description="Gemini APIキー"
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash-lite",
        alias="GEMINI_MODEL",
        description="使用するGeminiモデル名"
    )
    gemini_timeout_sec: int = Field(
        default=120,
        alias="GEMINI_TIMEOUT_SEC",
        description="Gemini API呼び出しのタイムアウト秒数"
    )
    
    # Quiz専用Gemini最適化設定
    quiz_gemini_model: str | None = Field(
        default=None,
        alias="QUIZ_GEMINI_MODEL",
        description="Quiz専用Geminiモデル名（未指定なら gemini_model を使用）"
    )
    quiz_gemini_max_output_tokens: int = Field(
        default=2048,
        alias="QUIZ_GEMINI_MAX_OUTPUT_TOKENS",
        description="Quiz生成時の最大出力トークン数"
    )
    quiz_gemini_temperature: float = Field(
        default=0.2,
        alias="QUIZ_GEMINI_TEMPERATURE",
        description="Quiz生成時の temperature"
    )
    
    # LLMプロバイダー選択
    llm_provider: str = Field(
        default="ollama",
        alias="LLM_PROVIDER",
        description="LLMプロバイダー（ollama または gemini）"
    )
```

---

## ステップ5: LLMクライアントファクトリの作成

`backend/app/llm/__init__.py`を更新（または新規作成）：

```python
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
```

---

## ステップ6: 使用箇所の更新

### 6.1 `backend/app/routers/ask.py`を更新

```python
# 変更前
from app.llm.ollama import get_ollama_client

# 変更後
from app.llm import get_llm_client

# 使用箇所
# 変更前
llm_client = get_ollama_client()

# 変更後
llm_client = get_llm_client()
```

### 6.2 `backend/app/quiz/generator.py`を更新

```python
# 変更前
from app.llm.ollama import get_ollama_client

# 変更後
from app.llm import get_llm_client

# 使用箇所
# 変更前
llm_client = get_ollama_client()

# 変更後
llm_client = get_llm_client()
```

---

## ステップ7: 動作確認

### 7.1 環境変数の確認

`.env`ファイルに以下が設定されていることを確認：

```env
GEMINI_API_KEY=your_api_key_here
LLM_PROVIDER=gemini
```

### 7.2 サーバー起動

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### 7.3 API動作確認

1. **QA機能の確認**
   ```bash
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "テスト質問"}'
   ```

2. **Quiz生成の確認**
   ```bash
   curl -X POST http://localhost:8000/quiz/generate \
     -H "Content-Type: application/json" \
     -d '{"level": "beginner", "count": 5}'
   ```

### 7.4 ログの確認

サーバーのログで以下を確認：
- `Gemini API回答取得成功` のログが表示されること
- エラーが発生していないこと

---

## トラブルシューティング

### エラー: "Gemini APIキーが設定されていません"

**原因**: `GEMINI_API_KEY`環境変数が設定されていない

**解決方法**:
1. `.env`ファイルに`GEMINI_API_KEY=your_api_key_here`を追加
2. サーバーを再起動

### エラー: "無効なLLMプロバイダー"

**原因**: `LLM_PROVIDER`環境変数が無効な値

**解決方法**:
1. `.env`ファイルに`LLM_PROVIDER=gemini`を追加（または`ollama`）
2. サーバーを再起動

### エラー: "Gemini API呼び出しエラー"

**原因**: APIキーが無効、またはAPIの制限に達している

**解決方法**:
1. APIキーが正しいか確認
2. [Google AI Studio](https://makersuite.google.com/app/apikey) でAPIキーの状態を確認
3. 使用量制限に達していないか確認

### タイムアウトエラー

**原因**: Gemini APIの応答が遅い、またはタイムアウト設定が短い

**解決方法**:
1. `.env`ファイルで`GEMINI_TIMEOUT_SEC`を増やす（例: `180`）
2. サーバーを再起動

---

## 切り戻し方法

Ollamaに戻す場合は、`.env`ファイルで以下を設定：

```env
LLM_PROVIDER=ollama
```

サーバーを再起動すれば、Ollamaに切り戻されます。

---

## 補足: Gemini APIの特徴

### Ollamaとの違い

| 項目 | Ollama | Gemini API |
|------|--------|------------|
| 実行環境 | ローカル | クラウド |
| APIキー | 不要 | 必要 |
| コスト | 無料 | 従量課金 |
| 速度 | ローカル環境に依存 | クラウド環境に依存 |
| モデル選択 | ローカルにインストールしたモデル | Googleが提供するモデル |

### 推奨モデル

- **QA機能**: `gemini-2.5-flash-lite`（高速でRPM制限が緩い）
- **Quiz生成**: `gemini-2.5-flash-lite`（JSON生成に適している、推奨）
- **高品質が必要な場合**: `gemini-2.5-pro`（より高精度だがRPM制限が厳しい）

---

## まとめ

この手順に従うことで、OllamaからGemini APIに移行できます。  
既存のコード（`LLMClient`インターフェース）を変更せずに、設定だけで切り替えられるようになっています。

**重要なポイント:**
- `LLMClient`インターフェースを実装することで、既存コードを変更せずに切り替え可能
- 環境変数`LLM_PROVIDER`でプロバイダーを選択
- エラーが発生した場合は、ログを確認してトラブルシューティングを参照
