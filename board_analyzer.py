"""
board_analyzer.py
-----------------
牌面纹理分析：连接度、花色结构、高牌结构、范围优势
这是翻后GTO建议的核心输入
"""

from collections import Counter
from poker_engine import RANK_VAL, Card


# ── 牌面纹理分析 ──────────────────────────────────────────

def analyze_board(board: list) -> dict:
    """
    分析公共牌纹理，返回结构化数据
    board: [Card, ...]  3-5张
    """
    if not board:
        return _empty_texture()

    vals  = sorted([c.val for c in board], reverse=True)
    suits = [c.suit for c in board]
    n     = len(board)

    # ── 花色结构 ──────────────────────────────────
    suit_counts = Counter(suits)
    max_suit    = max(suit_counts.values())

    if n == 3:
        if max_suit == 3:
            flush_texture = 'monotone'       # 三张同花，极端
        elif max_suit == 2:
            flush_texture = 'two_tone'       # 两张同花，有听牌
        else:
            flush_texture = 'rainbow'        # 三色，无同花听牌
    elif n >= 4:
        if max_suit >= 4:
            flush_texture = 'flush_possible' # 四张同花，已完成
        elif max_suit == 3:
            flush_texture = 'flush_draw'     # 三张同花，有听牌
        else:
            flush_texture = 'dry'

    # ── 连接度 ────────────────────────────────────
    unique_vals = sorted(set(vals), reverse=True)
    gaps = [unique_vals[i] - unique_vals[i+1] for i in range(len(unique_vals)-1)]

    # 是否有顺子（已完成）
    has_straight_on_board = False
    for i in range(len(unique_vals)-4):
        window = unique_vals[i:i+5]
        if window[0] - window[-1] == 4 and len(set(window)) == 5:
            has_straight_on_board = True

    # A-2-3-4-5 轮子
    if set([12,0,1,2,3]).issubset(set(unique_vals)):
        has_straight_on_board = True

    # 连接程度：最小gap的平均值越小说明越连
    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        min_gap = min(gaps)
    else:
        avg_gap = 99
        min_gap = 99

    if min_gap <= 1 and len([g for g in gaps if g <= 2]) >= 2:
        connectivity = 'very_connected'   # 如 8-7-6, 9-8-7-6
    elif min_gap <= 2 and avg_gap <= 2.5:
        connectivity = 'connected'        # 如 T-8-6, J-9-7
    elif avg_gap <= 3:
        connectivity = 'semi_connected'   # 如 K-9-5
    else:
        connectivity = 'dry'              # 如 A-7-2, K-8-3

    # ── 高牌结构 ──────────────────────────────────
    top_card = vals[0]
    if top_card >= 12:    # A high
        high_card = 'ace_high'
    elif top_card >= 11:  # K high
        high_card = 'king_high'
    elif top_card >= 9:   # Q/J high
        high_card = 'broadway'
    elif top_card >= 7:   # T/9 high
        high_card = 'mid_high'
    else:
        high_card = 'low'              # 8以下

    # ── 配对结构 ──────────────────────────────────
    val_counts = Counter(vals)
    max_freq   = max(val_counts.values())
    if max_freq >= 3:
        pair_structure = 'trips_on_board'
    elif max_freq == 2:
        pair_structure = 'paired'
    else:
        pair_structure = 'unpaired'

    # ── 威胁程度综合评分（0-10，越高说明牌面越危险/湿润）──
    danger = 0
    if flush_texture == 'two_tone':       danger += 2
    elif flush_texture == 'monotone':     danger += 4
    elif flush_texture == 'flush_draw':   danger += 3
    elif flush_texture == 'flush_possible': danger += 5
    if connectivity == 'very_connected':  danger += 4
    elif connectivity == 'connected':     danger += 2
    elif connectivity == 'semi_connected':danger += 1
    if has_straight_on_board:             danger += 2
    if pair_structure == 'paired':        danger -= 1   # 配对牌面听牌变少

    danger = min(10, max(0, danger))

    return {
        'vals':           vals,
        'n_cards':        n,
        'flush_texture':  flush_texture,
        'connectivity':   connectivity,
        'high_card':      high_card,
        'pair_structure': pair_structure,
        'has_straight_on_board': has_straight_on_board,
        'danger':         danger,           # 0=极干燥, 10=极湿润
        'top_val':        top_card,
        'is_wet':         danger >= 5,
        'is_dry':         danger <= 2,
        'suit_counts':    dict(suit_counts),
    }


def _empty_texture():
    return {
        'vals':[], 'n_cards':0, 'flush_texture':'rainbow',
        'connectivity':'dry', 'high_card':'low',
        'pair_structure':'unpaired', 'has_straight_on_board':False,
        'danger':0, 'top_val':0, 'is_wet':False, 'is_dry':True,
        'suit_counts':{},
    }


# ── 范围优势分析 ──────────────────────────────────────────

def range_advantage(board_texture: dict, hero_pos: str, villain_pos: str) -> dict:
    """
    简化的范围优势分析：
    判断这块牌面对谁更有利（谁的范围命中率更高）
    返回 'hero' / 'villain' / 'neutral'
    """
    t    = board_texture
    high = t['high_card']

    # BTN/CO 开牌范围更宽，低牌面通常 IP 方有优势
    ip_positions  = {'BTN', 'CO', 'HJ'}
    oop_positions = {'UTG', 'SB', 'BB'}

    hero_is_ip = hero_pos in ip_positions

    # 高牌面（A/K）：通常对翻前加注方有利（有更多AK/KQ）
    if high in ('ace_high', 'king_high'):
        if hero_is_ip:
            advantage = 'hero_slight'
        else:
            advantage = 'neutral'

    # 中低连牌面：对 IP 方/宽范围方有利（更多同花连牌）
    elif t['connectivity'] in ('very_connected', 'connected') and high in ('mid_high', 'low'):
        if hero_is_ip:
            advantage = 'hero_slight'
        else:
            advantage = 'villain_slight'

    # 干燥低牌面：对翻前加注方有利（范围强）
    elif t['is_dry'] and high == 'low':
        advantage = 'hero_slight' if hero_is_ip else 'neutral'

    else:
        advantage = 'neutral'

    return {
        'advantage':    advantage,
        'hero_is_ip':   hero_is_ip,
        'description_zh': _advantage_desc_zh(advantage, t),
        'description_en': _advantage_desc_en(advantage, t),
    }


def _advantage_desc_zh(adv, t):
    if adv == 'hero_slight':
        return f'这块{_texture_zh(t)}对你的范围略有利'
    if adv == 'villain_slight':
        return f'这块{_texture_zh(t)}对对手的范围略有利'
    return f'这块{_texture_zh(t)}对双方范围较中性'


def _advantage_desc_en(adv, t):
    if adv == 'hero_slight':
        return f'This {_texture_en(t)} board slightly favors your range'
    if adv == 'villain_slight':
        return f'This {_texture_en(t)} board slightly favors villain\'s range'
    return f'This {_texture_en(t)} board is relatively neutral'


def _texture_zh(t):
    parts = []
    if t['flush_texture'] == 'monotone':     parts.append('单色')
    elif t['flush_texture'] == 'two_tone':   parts.append('双色')
    if t['connectivity'] == 'very_connected':parts.append('高度连牌')
    elif t['connectivity'] == 'connected':   parts.append('连牌')
    if t['pair_structure'] == 'paired':      parts.append('配对')
    return ''.join(parts) + '牌面' if parts else '牌面'


def _texture_en(t):
    parts = []
    if t['flush_texture'] == 'monotone':     parts.append('monotone')
    elif t['flush_texture'] == 'two_tone':   parts.append('two-tone')
    if t['connectivity'] == 'very_connected':parts.append('very connected')
    elif t['connectivity'] == 'connected':   parts.append('connected')
    if t['pair_structure'] == 'paired':      parts.append('paired')
    return ' '.join(parts) + ' board' if parts else 'board'


# ── 手牌与牌面的关系 ──────────────────────────────────────

def hand_board_relation(hole_cards: list, board: list, board_texture: dict) -> dict:
    """
    分析你的手牌和牌面的具体关系：
    是否有顶对/超对/坚果/听牌/组合听牌等
    """
    if not board:
        return {'relation': 'preflop', 'draw_outs': 0}

    from poker_engine import best_hand_from_7, _has_flush_draw, _has_straight_draw, RANK_VAL

    hand_rank  = best_hand_from_7(hole_cards, board)[0]
    board_vals = sorted([c.val for c in board], reverse=True)
    hole_vals  = [c.val for c in hole_cards]
    max_hole   = max(hole_vals)
    min_hole   = min(hole_vals)

    flush_draw    = _has_flush_draw(hole_cards, board)
    straight_draw = _has_straight_draw(hole_cards, board)

    # 出牌数估算
    draw_outs = 0
    if flush_draw and straight_draw:
        draw_outs = 15   # combo draw
    elif flush_draw:
        draw_outs = 9
    elif straight_draw:
        draw_outs = 8

    # 是否是顶对/超对
    is_top_pair  = hand_rank == 1 and max_hole == board_vals[0]
    is_overpair  = hand_rank == 1 and min(hole_vals) > board_vals[0]  # 对子大于最大公共牌

    # 是否是坚果（近似判断）
    is_nut_flush    = flush_draw and max_hole == 12   # A高同花
    is_nut_straight = False  # 简化：不做坚果顺子判断

    # 是否超过两对面临威胁
    board_danger = board_texture['danger']
    hand_strength_vs_board = 'strong'
    if hand_rank >= 4:   # 顺子+
        if board_texture['has_straight_on_board'] and hand_rank == 4:
            hand_strength_vs_board = 'vulnerable'   # 可能被更高顺子超越
        else:
            hand_strength_vs_board = 'strong'
    elif hand_rank == 3:  # 三条
        hand_strength_vs_board = 'strong' if board_danger < 5 else 'moderate'
    elif hand_rank == 2:  # 两对
        hand_strength_vs_board = 'moderate' if board_danger < 6 else 'vulnerable'
    elif hand_rank == 1:  # 一对
        if is_overpair:
            hand_strength_vs_board = 'moderate' if board_danger < 5 else 'vulnerable'
        elif is_top_pair:
            hand_strength_vs_board = 'moderate' if board_danger < 4 else 'weak'
        else:
            hand_strength_vs_board = 'weak'
    else:  # 高牌
        hand_strength_vs_board = 'draw' if draw_outs > 0 else 'air'

    return {
        'hand_rank':     hand_rank,
        'is_top_pair':   is_top_pair,
        'is_overpair':   is_overpair,
        'is_nut_flush':  is_nut_flush,
        'flush_draw':    flush_draw,
        'straight_draw': straight_draw,
        'draw_outs':     draw_outs,
        'is_combo_draw': flush_draw and straight_draw,
        'hand_strength_vs_board': hand_strength_vs_board,
        'board_danger':  board_danger,
    }
