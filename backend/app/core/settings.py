"""
アプリケーション設定（環境変数・定数の一元管理）

【初心者向け】
- Pydantic Settings: 環境変数や.envを読んで型付きで扱うための仕組み
- ここで定義した値は app.core.settings.settings から参照できる
- 主な分類: CORS, ドキュメント/RAG, 検索, Quiz, Ollama(LLM)
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    アプリケーション設定クラス
    環境変数（または.env）の値が自動でここにマッピングされる
    """

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
    # 見出し境界優先チャンキング用設定
    section_chunk_size: int = Field(
        default=450,
        alias="SECTION_CHUNK_SIZE",
        description="セクション単位のチャンクサイズ（文字数）"
    )
    section_chunk_overlap: int = Field(
        default=100,
        alias="SECTION_CHUNK_OVERLAP",
        description="セクション単位のチャンクオーバーラップ（文字数）"
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
    
    # NEW: 候補品質管理（動的候補数）
    candidate_ratio: float = Field(
        default=0.005,
        alias="CANDIDATE_RATIO",
        description="候補数の割合（collection_count * ratio）"
    )
    candidate_min_k: int = Field(
        default=20,
        alias="CANDIDATE_MIN_K",
        description="候補数の最小値"
    )
    candidate_max_k: int = Field(
        default=60,
        alias="CANDIDATE_MAX_K",
        description="候補数の最大値"
    )
    
    # NEW: Cross-Encoder リランキング
    rerank_enabled: bool = Field(
        default=True,
        alias="RERANK_ENABLED",
        description="Cross-Encoderリランキングを有効化"
    )
    rerank_model: str = Field(
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        alias="RERANK_MODEL",
        description="Cross-Encoderモデル名（多言語対応）"
    )
    rerank_ratio: float = Field(
        default=0.3,
        alias="RERANK_RATIO",
        description="リランク対象数の割合（candidate_k * ratio）"
    )
    rerank_min_n: int = Field(
        default=8,
        alias="RERANK_MIN_N",
        description="リランク対象数の最小値"
    )
    rerank_max_n: int = Field(
        default=12,
        alias="RERANK_MAX_N",
        description="リランク対象数の最大値"
    )
    rerank_score_threshold: float = Field(
        default=-4.0,  # CHANGED: -2.5 → -4.0 に緩和（強盗質問で根拠が見つからない問題を解決）
        alias="RERANK_SCORE_THRESHOLD",
        description="Cross-Encoderスコア閾値（絶対値、これ以下は除外）"
    )
    rerank_score_gap_threshold: float = Field(
        default=6.0,
        alias="RERANK_SCORE_GAP_THRESHOLD",
        description="トップスコアとの差分閾値（これ以上離れている候補は除外、普遍的な品質管理）"
    )
    rerank_batch_size: int = Field(
        default=8,
        alias="RERANK_BATCH_SIZE",
        description="Cross-Encoderバッチサイズ"
    )
    rrf_k: int = Field(
        default=20,
        alias="RRF_K",
        description="RRF（順位融合）のKパラメータ（小さいほど上位重視）"
    )
    
    # Quiz専用検索設定（/ask とは独立、高速化重視）
    quiz_semantic_weight: float = Field(
        default=1.0,
        alias="QUIZ_SEMANTIC_WEIGHT",
        description="クイズ生成時のsemantic検索の重み（1.0=semantic単独）"
    )
    quiz_candidate_k: int = Field(
        default=10,
        alias="QUIZ_CANDIDATE_K",
        description="クイズ生成時の候補取得件数（semantic検索、高速化のため小さめ）"
    )
    quiz_context_top_n: int = Field(
        default=4,
        alias="QUIZ_CONTEXT_TOP_N",
        description="クイズ生成時にLLMに渡す引用の最大件数（厳格なタイムアウト対策）"
    )
    quiz_quote_max_len: int = Field(
        default=200,
        alias="QUIZ_QUOTE_MAX_LEN",
        description="クイズ生成時の引用（quote）の最大文字数（厳格なタイムアウト対策）"
    )
    quiz_total_quote_max_chars: int = Field(
        default=800,
        alias="QUIZ_TOTAL_QUOTE_MAX_CHARS",
        description="クイズ生成時の引用（quote）の総文字数上限（厳格なタイムアウト対策）"
    )
    quiz_rerank_enabled: bool = Field(
        default=False,
        alias="QUIZ_RERANK_ENABLED",
        description="クイズ生成時のリランキング有効化（高速化のため原則OFF）"
    )
    quiz_rerank_max_n: int = Field(
        default=6,
        alias="QUIZ_RERANK_MAX_N",
        description="クイズ生成時のリランク対象数上限（rerankを使う場合の制限）"
    )
    quiz_max_attempts: int = Field(
        default=10,  # CHANGED: 2 → 10 に増加（5問生成に対応、各試行で○×2件生成するため最低3回必要）
        alias="QUIZ_MAX_ATTEMPTS",
        description="クイズ生成の最大試行回数（各試行で○×2件生成するため、目標数に応じて調整）"
    )
    quiz_target_per_attempt: int = Field(
        default=3,
        alias="QUIZ_TARGET_PER_ATTEMPT",
        description="1回の生成で狙う問題数（短い出力で確実に返す）"
    )
    
    # Quiz専用サンプリング設定（教材からの出題に特化）
    quiz_pool_max_ids_per_source: int = Field(
        default=3000,
        alias="QUIZ_POOL_MAX_IDS_PER_SOURCE",
        description="Chunk Pool: 1sourceあたりの最大保持ID数"
    )
    quiz_pool_batch_size: int = Field(
        default=5000,
        alias="QUIZ_POOL_BATCH_SIZE",
        description="Chunk Pool: Chroma collection.get() のバッチサイズ"
    )
    quiz_sample_multiplier: int = Field(
        default=4,
        alias="QUIZ_SAMPLE_MULTIPLIER",
        description="サンプル数の倍率（sample_n = count * multiplier）"
    )
    quiz_sample_min_n: int = Field(
        default=20,
        alias="QUIZ_SAMPLE_MIN_N",
        description="サンプル数の最小値"
    )
    quiz_citations_min: int = Field(
        default=3,
        alias="QUIZ_CITATIONS_MIN",
        description="最低引用数（これ以下なら再取得）"
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
        default=120,
        alias="OLLAMA_TIMEOUT_SEC",
        description="Ollama API呼び出しのタイムアウト秒数（Quiz生成を考慮して長め）"
    )
    
    # Quiz専用Ollama最適化設定（JSON安定性と速度改善）
    quiz_ollama_model: str | None = Field(
        default=None,
        alias="QUIZ_OLLAMA_MODEL",
        description="Quiz専用モデル名（未指定なら ollama_model を使用）"
    )
    quiz_ollama_num_predict: int = Field(
        default=800,  # CHANGED: 400 → 800（長いstatement対応、途中で切れる問題を解決）
        alias="QUIZ_OLLAMA_NUM_PREDICT",
        description="Quiz生成時の最大トークン数（長いstatement対応、800推奨）"
    )
    quiz_ollama_num_ctx: int = Field(
        default=4096,
        alias="QUIZ_OLLAMA_NUM_CTX",
        description="Quiz生成時のコンテキスト上限（長すぎ防止）"
    )
    quiz_ollama_temperature: float = Field(
        default=0.2,
        alias="QUIZ_OLLAMA_TEMPERATURE",
        description="Quiz生成時の temperature（タイムアウト対策、大幅に下げる）"
    )
    quiz_force_json: bool = Field(
        default=True,
        alias="QUIZ_FORCE_JSON",
        description="Quiz生成時に format=json を強制（JSON安定性向上、○のみ生成で推奨）"
    )

    # Gemini API設定
    gemini_api_key: str = Field(
        default="",
        alias="GEMINI_API_KEY",
        description="Gemini APIキー"
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash-lite",
        alias="GEMINI_MODEL",
        description="使用するGeminiモデル名（gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro など）"
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

    # Pydantic v2の設定（Configクラスの代わりにmodel_configを使用）
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,  # Fieldのaliasとフィールド名の両方で読み込み可能
        extra="ignore"  # 未定義の環境変数を無視（ANONYMIZED_TELEMETRYなど）
    )


# グローバル設定インスタンス
settings = Settings()
