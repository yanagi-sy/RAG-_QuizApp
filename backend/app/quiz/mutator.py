"""
Quiz Statement Mutator（○→×変換）
"""
import re
import logging

# ロガー設定
logger = logging.getLogger(__name__)

# 反転ルール（優先度順）
NEGATION_RULES = [
    # 数値の反転（+1 / -1）
    (r"(\d+)個", lambda m: f"{int(m.group(1)) + 1}個"),
    (r"(\d+)件", lambda m: f"{int(m.group(1)) + 1}件"),
    (r"(\d+)回", lambda m: f"{int(m.group(1)) + 1}回"),
    (r"(\d+)日", lambda m: f"{int(m.group(1)) + 1}日"),
    (r"(\d+)時間", lambda m: f"{int(m.group(1)) + 1}時間"),
    (r"(\d+)分", lambda m: f"{int(m.group(1)) + 1}分"),
    (r"(\d+)秒", lambda m: f"{int(m.group(1)) + 1}秒"),
    (r"(\d+)人", lambda m: f"{int(m.group(1)) + 1}人"),
    (r"(\d+)円", lambda m: f"{int(m.group(1)) + 1}円"),
    
    # 禁止・許可の反転
    ("禁止されている", "許可されている"),
    ("禁止である", "許可される"),
    ("禁止する", "許可する"),
    ("してはいけない", "してもよい"),
    ("してはならない", "してもよい"),
    ("行ってはいけない", "行ってもよい"),
    ("行ってはならない", "行ってもよい"),
    
    # 必須・任意の反転
    ("必ず行う", "行わなくてもよい"),
    ("必ず確認する", "確認しなくてもよい"),
    ("必ず連絡する", "連絡しなくてもよい"),
    ("必ず報告する", "報告しなくてもよい"),
    ("必須である", "任意である"),
    ("必要である", "不要である"),
    ("必要がある", "必要がない"),
    
    # 順序の反転
    ("最初に", "最後に"),
    ("第一に", "第二に"),
    ("先に", "後に"),
    ("前に", "後に"),
    
    # その他の反転
    ("すべて", "一部"),
    ("常に", "時には"),
    ("すぐに", "後で"),
    ("直ちに", "後で"),
    ("即座に", "後で"),
]


def make_false_statement(statement: str) -> str:
    """
    ○（正しい断言文）から×（誤った断言文）を生成
    
    戦略（優先度順）:
    1. 数値の反転（+1 / -1）
    2. 禁止/許可の反転
    3. 必須/任意の反転
    4. 順序の反転
    5. その他の反転
    
    Args:
        statement: 正しい断言文（○）
        
    Returns:
        誤った断言文（×）
        
    Note:
        - 必ず1箇所以上の変更を加える
        - 変更できない場合は元の文をそのまま返す（validator で弾かれる）
    """
    original = statement
    
    # 各ルールを試す
    for rule in NEGATION_RULES:
        if isinstance(rule, tuple) and len(rule) == 2:
            # 単純な文字列置換
            pattern, replacement = rule
            
            if isinstance(pattern, str):
                # 文字列置換
                if pattern in statement:
                    mutated = statement.replace(pattern, replacement, 1)  # 最初の1回だけ置換
                    if mutated != original:
                        logger.info(f"Mutator成功: '{pattern}' -> '{replacement}'")
                        return mutated
            else:
                # 正規表現置換
                match = pattern.search(statement)
                if match:
                    mutated = pattern.sub(replacement, statement, count=1)
                    if mutated != original:
                        logger.info(f"Mutator成功（正規表現）: {pattern.pattern}")
                        return mutated
    
    # どのルールにも該当しなかった場合
    logger.warning(f"Mutator失敗: 変換ルールが見つかりませんでした: {statement[:50]}")
    
    # 最後の手段: 否定化（雑な方法だが変化させる）
    # "である" → "ではない", "する" → "しない" など
    if statement.endswith("である。"):
        return statement[:-4] + "ではない。"
    elif statement.endswith("する。"):
        return statement[:-3] + "しない。"
    elif statement.endswith("できる。"):
        return statement[:-4] + "できない。"
    elif statement.endswith("される。"):
        return statement[:-4] + "されない。"
    elif statement.endswith("ある。"):
        return statement[:-3] + "ない。"
    
    # 変更できない場合は元の文をそのまま返す（validator で弾かれる）
    logger.warning(f"Mutator失敗: 最終手段も該当せず: {statement[:50]}")
    return original
