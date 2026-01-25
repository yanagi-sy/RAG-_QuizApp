"""
Quiz専用 Chunk Pool（資料ごとのチャンクID一覧）

【初心者向け】
- Chroma の全チャンクを source ごとにID一覧として保持。検索せずランダムサンプル用
- 初回アクセスでビルドしメモリにキャッシュ。threading.Lock で排他制御
- 1 source あたり最大 quiz_pool_max_ids_per_source 件。バッチ取得でメモリ節約
- Unicode NFC 正規化でキーを統一（macOS NFD 対策）
"""
import logging
import random
import threading
import unicodedata
from typing import Dict, List, Optional

import chromadb

from app.core.settings import settings

# ロガー設定
logger = logging.getLogger(__name__)

# グローバルキャッシュ（起動時に1回だけビルド）
_pool_cache: Optional[Dict[str, List[str]]] = None
_pool_lock = threading.Lock()


def build_pool(collection: chromadb.Collection) -> Dict[str, List[str]]:
    """
    sourceごとの chunk ID poolを作成（メモリキャッシュ）
    
    Unicode正規化(NFC)で source を揃えてキー化（NFD/NFC混在対策）
    大規模対策:
    - 1sourceあたり最大 quiz_pool_max_ids_per_source まで保持
    - バッチ取得（offset/limit）で全件一括を避ける
    
    Args:
        collection: ChromaDBコレクション
        
    Returns:
        { source_norm: [id1, id2, ...] } の辞書
    """
    try:
        # 全データ件数を取得
        total_count = collection.count()
        
        if total_count == 0:
            logger.warning("[ChunkPool] コレクションが空です")
            return {}
        
        # バッチサイズ設定
        batch_size = settings.quiz_pool_batch_size
        max_ids_per_source = settings.quiz_pool_max_ids_per_source
        
        # sourceごとにIDを集計（NFC正規化）
        pool: Dict[str, List[str]] = {}
        offset = 0
        
        logger.info(f"[ChunkPool] build開始: total_count={total_count}, batch_size={batch_size}")
        
        # バッチ取得でメモリ効率を確保
        while offset < total_count:
            # バッチ取得（include=["metadatas"] で軽量化）
            results = collection.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"]
            )
            
            ids = results.get("ids", [])
            metadatas = results.get("metadatas", [])
            
            if len(ids) == 0:
                break
            
            # sourceごとにIDを集計
            for chunk_id, metadata in zip(ids, metadatas):
                source_raw = metadata.get("source", "unknown")
                # NFC正規化（macOS NFD対策）
                source_norm = unicodedata.normalize("NFC", source_raw)
                
                if source_norm not in pool:
                    pool[source_norm] = []
                
                # 大規模対策: 1sourceあたり max_ids_per_source まで
                if len(pool[source_norm]) < max_ids_per_source:
                    pool[source_norm].append(chunk_id)
            
            offset += len(ids)
            logger.info(f"[ChunkPool] バッチ処理中: {offset}/{total_count}")
        
        # ログ出力
        source_counts = {src: len(ids_list) for src, ids_list in pool.items()}
        logger.info(f"[ChunkPool] build完了: {len(pool)} sources, total_ids={total_count}")
        logger.info(f"[ChunkPool] source分布: {source_counts}")
        
        return pool
    
    except Exception as e:
        logger.error(f"[ChunkPool] build失敗: {type(e).__name__}: {e}")
        return {}


def get_pool(collection: chromadb.Collection, force_rebuild: bool = False) -> Dict[str, List[str]]:
    """
    Chunk Pool を取得（lazy build + cache + thread-safe）
    
    Args:
        collection: ChromaDBコレクション
        force_rebuild: キャッシュを無視して再ビルド
        
    Returns:
        { source_norm: [id1, id2, ...] } の辞書
    """
    global _pool_cache
    
    # 並列アクセス対策（threading.Lock）
    with _pool_lock:
        if force_rebuild or _pool_cache is None:
            _pool_cache = build_pool(collection)
        
        return _pool_cache


def get_ids_for_source(
    pool: Dict[str, List[str]],
    source: str
) -> List[str]:
    """
    指定sourceのchunk IDリストを取得
    
    Args:
        pool: chunk pool
        source: source名（自動でNFC正規化される）
        
    Returns:
        chunk IDのリスト
    """
    source_norm = unicodedata.normalize("NFC", source)
    
    # 【デバッグ】poolのキーとsourceのマッチングを確認
    if source_norm not in pool:
        # poolのキーもNFC正規化して比較
        pool_keys_norm = {unicodedata.normalize("NFC", k): k for k in pool.keys()}
        matched_key = pool_keys_norm.get(source_norm)
        
        if matched_key:
            logger.info(
                f"[ChunkPool] get_ids_for_source: source_norm={source_norm} がpoolに直接存在しないが、"
                f"正規化後のキー {matched_key} でマッチしました"
            )
            return pool.get(matched_key, [])
        else:
            logger.warning(
                f"[ChunkPool] get_ids_for_source: source_norm={source_norm} がpoolに存在しません。"
                f"pool_keys={list(pool.keys())[:5]}..."
            )
            return []
    
    return pool.get(source_norm, [])


def sample_ids(
    pool: Dict[str, List[str]],
    source: str,
    n: int,
    seed: Optional[str] = None
) -> List[str]:
    """
    指定sourceから n 件のchunk IDをランダムサンプル（重複なし）
    
    Args:
        pool: chunk pool
        source: source名
        n: サンプル数
        seed: 乱数シード（再現性確保）
        
    Returns:
        chunk IDのリスト（最大 n 件、不足の場合は全件返却）
    """
    ids = get_ids_for_source(pool, source)
    
    if len(ids) == 0:
        return []
    
    # サンプル数を調整（不足の場合は全件）
    sample_n = min(n, len(ids))
    
    # ランダムサンプル
    if seed:
        rng = random.Random(seed)
        return rng.sample(ids, sample_n)
    else:
        return random.sample(ids, sample_n)


def sample_ids_multi_source(
    pool: Dict[str, List[str]],
    sources: Optional[List[str]],
    n: int,
    seed: Optional[str] = None
) -> List[str]:
    """
    複数sourceから均等に n 件のchunk IDをランダムサンプル
    
    Args:
        pool: chunk pool
        sources: source名のリスト（Noneなら全source対象）
        n: サンプル数
        seed: 乱数シード（再現性確保）
        
    Returns:
        chunk IDのリスト（最大 n 件）
    """
    # source一覧を取得
    if sources:
        # 【品質担保】単一ソース固定のため、sourcesは1件のみであることを確認
        if len(sources) > 1:
            logger.error(
                f"[ChunkPool] sample_ids_multi_source: sourcesが複数指定されています（{len(sources)}件）。"
                f"単一ソース固定のため、最初の1件のみを使用します。"
            )
            sources = [sources[0]]
        
        # 指定されたsourceのみ（NFC正規化）
        target_sources_norm = [unicodedata.normalize("NFC", s) for s in sources]
        # poolのキーもNFC正規化して比較
        pool_keys_norm = {unicodedata.normalize("NFC", k): k for k in pool.keys()}
        target_sources = []
        
        for source_norm in target_sources_norm:
            matched_key = pool_keys_norm.get(source_norm)
            if matched_key:
                target_sources.append(matched_key)
                logger.info(
                    f"[ChunkPool] sourceマッチング成功: specified={source_norm} -> pool_key={matched_key}"
                )
            else:
                # 【品質担保】マッチしない場合はエラーログを出力し、そのsourceをスキップ
                logger.error(
                    f"[ChunkPool] 【重大】指定されたsourceがpoolに存在しません: "
                    f"specified={source_norm}, pool_keys={list(pool.keys())[:10]}"
                )
        
        # 【品質担保】target_sourcesが空の場合はエラーを返す（全sourceからサンプルしない）
        if len(target_sources) == 0:
            logger.error(
                f"[ChunkPool] 【重大】指定されたsourceがpoolに存在しません。空のリストを返します。"
                f"指定source: {sources}, poolのキー: {list(pool.keys())[:10]}"
            )
            return []
    else:
        # 全source（ただし、単一ソース固定のため通常は使用されない）
        logger.warning(
            f"[ChunkPool] sample_ids_multi_source: sourcesがNoneです。"
            f"単一ソース固定のため、このケースは通常発生しません。"
        )
        target_sources = list(pool.keys())
    
    if len(target_sources) == 0:
        logger.warning("[ChunkPool] 対象sourceが存在しません")
        return []
    
    # 各sourceから均等にサンプル
    per_source = max(1, n // len(target_sources))
    remainder = n % len(target_sources)
    
    sampled_ids = []
    rng = random.Random(seed) if seed else random
    
    # 【デバッグ】target_sourcesとpoolのキーを確認
    logger.info(
        f"[ChunkPool] sample_ids_multi_source: "
        f"target_sources={target_sources}, "
        f"pool_keys={list(pool.keys())[:5]}..., "
        f"n={n}"
    )
    
    for i, source in enumerate(target_sources):
        # 余りを先頭のsourceに振り分け
        sample_n = per_source + (1 if i < remainder else 0)
        
        ids = get_ids_for_source(pool, source)
        logger.info(
            f"[ChunkPool] source={source}: ids_count={len(ids)}, sample_n={sample_n}"
        )
        
        if len(ids) == 0:
            logger.error(
                f"[ChunkPool] source={source} からidsが0件です。"
                f"このsourceはスキップされますが、結果として空のリストが返される可能性があります。"
            )
            continue
        
        sample_n = min(sample_n, len(ids))
        sampled = rng.sample(ids, sample_n) if seed else random.sample(ids, sample_n)
        sampled_ids.extend(sampled)
        
        logger.info(
            f"[ChunkPool] source={source}: {len(sampled)}件をサンプル（total={len(sampled_ids)}件）"
        )
    
    # 【品質担保】sampled_idsが空の場合、エラーログを出力
    if len(sampled_ids) == 0:
        logger.error(
            f"[ChunkPool] sample_ids_multi_source: サンプルされたIDが0件です。"
            f"target_sources={target_sources}, sources={sources}"
        )
    
    # n 件を超えた場合は切り詰め
    if len(sampled_ids) > n:
        if seed:
            rng.shuffle(sampled_ids)
        else:
            random.shuffle(sampled_ids)
        sampled_ids = sampled_ids[:n]
    
    return sampled_ids
