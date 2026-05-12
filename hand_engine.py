"""
hand_engine.py
--------------
多街手牌状态机：管理从翻前到河牌的完整手牌流程
每条街保存行动历史，让对手行动真正影响决策建议
"""

import random
import uuid
from dataclasses import dataclass, field
from typing import Optional
from board_analyzer import analyze_board, range_advantage, hand_board_relation
from poker_engine import (
    Deck, Card, best_hand_from_7, calc_equity,
    classify_hole, POSITIONS_6MAX, pot_odds,
    _has_flush_draw, _has_straight_draw, RANK_VAL
)
from villain_simulator import VillainSimulator
from opponents import generate_opponent

STREETS = ['preflop', 'flop', 'turn', 'river']


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class StreetState:
    street:              str
    board:               list
    new_cards:           list
    pot:                 float
    stack:               float
    hero_action:         Optional[str]  = None
    villain_action:      Optional[dict] = None
    gto_action:          Optional[str]  = None
    gto_reason_zh:       Optional[str]  = None
    gto_reason_en:       Optional[str]  = None
    exploit_action:      Optional[str]  = None
    exploit_reason_zh:   Optional[str]  = None
    exploit_reason_en:   Optional[str]  = None
    is_correct:          Optional[bool] = None
    hero_equity:         Optional[float]= None
    bet_sizing:          Optional[dict] = None   # {villain_bet, pot_odds_needed, ev_info}


@dataclass
class HandState:
    hand_id:        str
    hero_pos:       str
    villain_pos:    str
    hero_hole:      list
    opponent:       dict
    archetype:      str
    streets:        list  = field(default_factory=list)
    current_street: str   = 'preflop'
    board:          list  = field(default_factory=list)
    pot:            float = 0.0
    stack:          float = 100.0
    is_complete:    bool  = False
    villain_sim:    object = None

    def to_dict(self):
        return {
            'hand_id':        self.hand_id,
            'hero_pos':       self.hero_pos,
            'villain_pos':    self.villain_pos,
            'hero_hole':      [c.to_dict() for c in self.hero_hole],
            'hand_str':       classify_hole(self.hero_hole),
            'opponent':       self.opponent,
            'archetype':      self.archetype,
            'board':          [c.to_dict() for c in self.board],
            'pot':            round(self.pot, 1),
            'stack':          round(self.stack, 1),
            'current_street': self.current_street,
            'is_complete':    self.is_complete,
            'streets': [_street_to_dict(s) for s in self.streets],
        }


def _street_to_dict(s: StreetState) -> dict:
    return {
        'street':             s.street,
        'board':              [c.to_dict() for c in s.board],
        'new_cards':          [c.to_dict() for c in s.new_cards],
        'pot':                round(s.pot, 1),
        'stack':              round(s.stack, 1),
        'hero_action':        s.hero_action,
        'villain_action':     s.villain_action,
        'gto_action':         s.gto_action,
        'gto_reason_zh':      s.gto_reason_zh,
        'gto_reason_en':      s.gto_reason_en,
        'exploit_action':     s.exploit_action,
        'exploit_reason_zh':  s.exploit_reason_zh,
        'exploit_reason_en':  s.exploit_reason_en,
        'is_correct':         s.is_correct,
        'hero_equity':        s.hero_equity,
        'bet_sizing':         s.bet_sizing,
    }


# ── 手牌工厂 ──────────────────────────────────────────────

def start_new_hand(archetype: str = None) -> HandState:
    """开始一手新牌，返回翻前决策点"""
    deck = Deck().shuffle()

    hero_pos    = random.choice(POSITIONS_6MAX)
    villain_pos = random.choice([p for p in POSITIONS_6MAX if p != hero_pos])

    hero_hole = deck.deal(2)
    opp       = generate_opponent(archetype)
    villain   = VillainSimulator(opp['archetype'])

    pot   = 1.5
    stack = round(random.uniform(80, 120), 0)

    hand = HandState(
        hand_id     = str(uuid.uuid4())[:8],
        hero_pos    = hero_pos,
        villain_pos = villain_pos,
        hero_hole   = hero_hole,
        opponent    = opp,
        archetype   = opp['archetype'],
        pot         = pot,
        stack       = stack,
        villain_sim = villain,
    )

    gto_a, gto_zh, gto_en, exp_a, exp_zh, exp_en = _preflop_advice(
        hero_hole, hero_pos, opp
    )

    hand.streets.append(StreetState(
        street            = 'preflop',
        board             = [],
        new_cards         = [],
        pot               = pot,
        stack             = stack,
        gto_action        = gto_a,
        gto_reason_zh     = gto_zh,
        gto_reason_en     = gto_en,
        exploit_action    = exp_a,
        exploit_reason_zh = exp_zh,
        exploit_reason_en = exp_en,
    ))
    return hand


def apply_hero_action(hand: HandState, hero_action: str) -> HandState:
    """
    处理 hero 的行动 → 触发对手反应 → 推进到下一街
    """
    current = hand.streets[-1]
    current.hero_action = hero_action

    # 判断是否正确（用剥削建议作为标准）
    target = current.exploit_action or current.gto_action or 'check'
    current.is_correct = _normalize(hero_action) == _normalize(target)

    # hero 弃牌，手牌结束
    if hero_action == 'fold':
        hand.is_complete = True
        return hand

    # 更新底池
    _update_pot(hand, hero_action, current.street)

    # 翻前对手反应
    villain = hand.villain_sim
    if current.street == 'preflop':
        v_act = villain.preflop_action(hero_raised=hero_action in ['raise', '3bet', '4bet'])
        current.villain_action = v_act
        if v_act['action'] == 'fold':
            hand.is_complete = True
            return hand

    # 进入下一街
    next_street = _next_street(current.street)
    if next_street is None:
        hand.is_complete = True
        return hand

    hand.current_street = next_street

    # 发公共牌（从剩余牌堆）
    deck = Deck().shuffle()
    deck.remove(hand.hero_hole + hand.board)
    new_cards = deck.deal(3 if next_street == 'flop' else 1)
    hand.board.extend(new_cards)

    # 翻后对手先行动（check or bet）
    if next_street == 'flop':
        v_act = villain.flop_action(hero_bet=False)
    elif next_street == 'turn':
        v_act = villain.turn_action(hero_bet=False)
    else:
        v_act = villain.river_action(hero_bet=False)

    # 权益计算
    equity = _quick_equity(hand.hero_hole, hand.board)

    # 翻后建议
    gto_a, gto_zh, gto_en, exp_a, exp_zh, exp_en = _postflop_advice(
        hand.hero_hole, hand.board, next_street,
        hand.pot, hand.stack, hand.opponent, v_act
    )

    sizing = calc_sizing(hand.pot, hand.stack, v_act)

    hand.streets.append(StreetState(
        street            = next_street,
        board             = list(hand.board),
        new_cards         = new_cards,
        pot               = round(hand.pot, 1),
        stack             = round(hand.stack, 1),
        villain_action    = v_act,
        gto_action        = gto_a,
        gto_reason_zh     = gto_zh,
        gto_reason_en     = gto_en,
        exploit_action    = exp_a,
        exploit_reason_zh = exp_zh,
        exploit_reason_en = exp_en,
        hero_equity       = equity,
        bet_sizing        = sizing,
    ))
    return hand


def finalize_hand(hand: HandState) -> dict:
    """河牌结束后生成完整手牌总结"""
    decided = [s for s in hand.streets if s.hero_action is not None]
    correct = sum(1 for s in decided if s.is_correct)
    total   = len(decided)
    pct     = round(correct / total * 100) if total else 0

    street_reviews = []
    for s in decided:
        street_reviews.append({
            'street':           s.street,
            'hero_action':      s.hero_action,
            'gto_action':       s.gto_action,
            'exploit_action':   s.exploit_action,
            'is_correct':       s.is_correct,
            'reason_zh':        s.exploit_reason_zh or s.gto_reason_zh or '',
            'reason_en':        s.exploit_reason_en or s.gto_reason_en or '',
            'villain_action':   s.villain_action,
            'equity':           s.hero_equity,
        })

    villain_read = hand.villain_sim.get_read() if hand.villain_sim else {'zh': [], 'en': []}
    mistakes     = [r for r in street_reviews if not r['is_correct']]

    return {
        'hand_id':        hand.hand_id,
        'hero_hole':      [c.to_dict() for c in hand.hero_hole],
        'hand_str':       classify_hole(hand.hero_hole),
        'board':          [c.to_dict() for c in hand.board],
        'archetype':      hand.archetype,
        'opponent_name':  hand.opponent.get('name', ''),
        'correct':        correct,
        'total':          total,
        'pct':            pct,
        'street_reviews': street_reviews,
        'villain_read':   villain_read,
        'mistakes':       mistakes,
        'hero_pos':       hand.hero_pos,
        'villain_pos':    hand.villain_pos,
    }


# ── 策略建议 ──────────────────────────────────────────────

def _preflop_advice(hole_cards, position, opponent):
    """
    返回 (gto_action, gto_zh, gto_en, exploit_action, exploit_zh, exploit_en)
    GTO 建议基于位置+手牌强度
    剥削建议额外考虑对手形象
    """
    hand_str  = classify_hole(hole_cards)
    archetype = opponent.get('archetype', 'tag')
    stats     = opponent.get('stats', {})
    fold_3bet = stats.get('fold_to_3bet', 55)
    vpip      = stats.get('vpip', 25)

    r1 = hole_cards[0] if hole_cards[0].val >= hole_cards[1].val else hole_cards[1]
    r2 = hole_cards[1] if hole_cards[0].val >= hole_cards[1].val else hole_cards[0]
    is_pair   = r1.rank == r2.rank
    is_suited = r1.suit == r2.suit
    hi, lo    = r1.val, r2.val
    gap       = hi - lo
    pos_idx   = POSITIONS_6MAX.index(position)  # 0=UTG … 5=BB

    # ── GTO 建议 ──
    gto_a, gto_zh, gto_en = _gto_preflop_rule(
        is_pair, is_suited, hi, lo, gap, pos_idx, hand_str
    )

    # ── 剥削调整 ──
    exp_a   = gto_a
    exp_zh  = gto_zh
    exp_en  = gto_en

    if gto_a == 'raise':
        if archetype == 'nit' and fold_3bet > 65:
            exp_zh = f'标准开牌。对手是Nit（Fold 3bet={fold_3bet}%），对手很少3bet，开牌范围可以稍微扩大。'
            exp_en = f'Standard raise. Villain is a Nit (Fold 3-bet={fold_3bet}%), rarely 3-bets — slightly widen open range.'
        elif archetype in ['fish', 'calling_station']:
            exp_zh = f'开牌建立底池。对手VPIP={vpip}%，会用很多弱牌入池，强化价值。'
            exp_en = f'Raise to build pot. Villain VPIP={vpip}% — calls with many weak hands, great for value.'
        elif archetype == 'lag' and fold_3bet < 45:
            exp_zh = f'开牌，但注意对手是LAG（Fold 3bet={fold_3bet}%），可能3bet。手牌够强可以4bet还击。'
            exp_en = f'Raise, but careful — villain is LAG (Fold 3-bet={fold_3bet}%), likely to 3-bet. Strong enough to 4-bet if so.'

    elif gto_a == 'fold':
        if archetype == 'nit' and pos_idx >= 3 and is_suited and gap <= 2:
            exp_a   = 'raise'
            exp_zh  = f'GTO弃牌，但对手是Nit（VPIP={vpip}%）。在后位同花连牌可以steal盲注。'
            exp_en  = f'GTO fold, but villain is Nit (VPIP={vpip}%). In position with suited connector — steal attempt is profitable.'

    return gto_a, gto_zh, gto_en, exp_a, exp_zh, exp_en


def _gto_preflop_rule(is_pair, is_suited, hi, lo, gap, pos_idx, hand_str):
    """
    6人桌 GTO 开牌范围（参考真实 GTO solver 标准范围）
    pos_idx: 0=UTG, 1=HJ, 2=CO, 3=BTN, 4=SB, 5=BB
    """
    def r(zh, en): return 'raise', zh, en
    def f(zh, en): return 'fold', zh, en

    s = '同花' if is_suited else ''
    se = 'suited ' if is_suited else ''

    # ── 对子 ──
    # RANK_VAL pairs: AA=12,KK=11,QQ=10,JJ=9,TT=8,99=7,88=6,77=5,66=4,55=3,44=2,33=1,22=0
    if is_pair:
        if hi >= 7:    # 99+(hi>=7) — any position
            return r(f'{hand_str} 强对子，任何位置标准开牌 2.5bb。',
                     f'{hand_str} strong pair — open 2.5bb any position.')
        if hi >= 4:    # 66-88 (hi 4,5,6) — any position
            return r(f'{hand_str} 中等对子，Set隐含赔率好，任何位置可开牌。',
                     f'{hand_str} mid pair — good set mining value, open any position.')
        if hi >= 2:    # 44-55 (hi 2,3) — HJ+
            if pos_idx >= 1:
                return r(f'{hand_str} 小对子，HJ+位置有足够隐含赔率。',
                         f'{hand_str} small pair — open HJ+ for set mining.')
            return f(f'{hand_str} 小对子在UTG范围外，弃牌。',
                     f'{hand_str} too small to open UTG — fold.')
        # 22-33 (hi 0,1) — CO+
        if pos_idx >= 2:
            return r(f'{hand_str} 最小对子，CO+开牌。',
                     f'{hand_str} smallest pair — CO+ only.')
        return f(f'{hand_str} 位置不够，弃牌。', f'{hand_str} fold.')

    # ── A高 ──
    # RANK_VAL: A=12,K=11,Q=10,J=9,T=8,9=7,8=6,7=5,6=4,5=3,4=2,3=1,2=0
    if hi == 12:
        if lo >= 8:    # AK(lo=11),AQ(lo=10),AJ(lo=9),AT(lo=8) — any position
            return r(f'{hand_str} 强A高，任何位置标准开牌。',
                     f'{hand_str} strong ace — open any position.')
        if lo == 7:    # A9 (lo=7)
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}A9，任何位置或HJ+可开牌。',
                         f'{hand_str} {se}A9 — open HJ+ or suited.')
            return f(f'{hand_str} A9o在UTG偏弱，弃牌。', f'{hand_str} A9o UTG — fold.')
        if lo == 6:    # A8 (lo=6)
            if is_suited:
                return r(f'{hand_str} 同花A8，任何位置有可玩性。',
                         f'{hand_str} A8s — open any position.')
            if pos_idx >= 1:
                return r(f'{hand_str} A8o在HJ+有足够权益，标准开牌。',
                         f'{hand_str} A8o — open HJ+.')
            return f(f'{hand_str} A8o在UTG偏弱，弃牌。', f'{hand_str} A8o UTG — fold.')
        if lo == 5:    # A7 (lo=5)
            if is_suited:
                return r(f'{hand_str} 同花A7，HJ+开牌，有轮子顺子潜力。',
                         f'{hand_str} A7s — HJ+ open, wheel potential.')
            if pos_idx >= 3:
                return r(f'{hand_str} A7o仅BTN+开牌。', f'{hand_str} A7o BTN+ only.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')
        if lo >= 3:    # A6(lo=4), A5(lo=3) — suited 3bet bluff hands
            if is_suited:
                return r(f'{hand_str} 同花小A，优质3bet bluff手牌，HJ+开牌。',
                         f'{hand_str} suited small ace — great 3-bet bluff, HJ+ open.')
            if pos_idx >= 3:
                return r(f'{hand_str} 非同花小A，BTN+可开牌。',
                         f'{hand_str} offsuit small ace — BTN+ only.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')
        if lo >= 0:    # A4(lo=2), A3(lo=1), A2(lo=0)
            if is_suited and pos_idx >= 2:
                return r(f'{hand_str} 同花小A，CO+开牌。',
                         f'{hand_str} suited small ace CO+ open.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')

    # ── K高 ──
    if hi == 11:
        if lo >= 10:   # KQ
            return r(f'{hand_str} 强手牌，任何位置开牌。',
                     f'{hand_str} strong hand — open any position.')
        if lo >= 9:    # KJ
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}KJ，HJ+开牌。',
                         f'{hand_str} {se}KJ — open HJ+.')
            return f(f'{hand_str} KJo在UTG偏弱，弃牌。', f'{hand_str} KJo UTG — fold.')
        if lo >= 8:    # KT (T=8 in RANK_VAL) — HJ+
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}KT，HJ+开牌。',
                         f'{hand_str} {se}KT — HJ+ open.')
            return f(f'{hand_str} KTo在UTG偏弱，弃牌。', f'{hand_str} KTo UTG — fold.')
        if lo >= 7:    # K9 — CO+ suited, BTN+ offsuit
            if is_suited and pos_idx >= 2:
                return r(f'{hand_str} 同花K9，CO+开牌。', f'{hand_str} K9s CO+ open.')
            if not is_suited and pos_idx >= 3:
                return r(f'{hand_str} K9o仅BTN+开牌。', f'{hand_str} K9o BTN+ only.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')
        if lo == 6:    # K8 (8=6 in RANK_VAL) — CO+ suited, BTN+ offsuit
            if is_suited and pos_idx >= 2:
                return r(f'{hand_str} 同花K8，CO+开牌。', f'{hand_str} K8s CO+ open.')
            if not is_suited and pos_idx >= 3:
                return r(f'{hand_str} K8o仅BTN+开牌。', f'{hand_str} K8o BTN+ only.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')
        if lo == 5 and is_suited and pos_idx >= 2:  # K7s — CO+
            return r(f'{hand_str} 同花K7，CO+开牌。', f'{hand_str} K7s CO+ open.')
        return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')

    # ── Q高 ──
    # QJ=lo9, QT=lo8, Q9=lo7
    if hi == 10:
        if lo == 9:    # QJ
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}QJ，HJ+开牌。',
                         f'{hand_str} {se}QJ — HJ+ open.')
            return f(f'{hand_str} QJo在UTG偏弱，弃牌。', f'{hand_str} QJo UTG — fold.')
        if lo == 8:    # QT
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}QT，HJ+开牌。',
                         f'{hand_str} {se}QT — HJ+ open.')
            return f(f'{hand_str} QTo在UTG偏弱，弃牌。', f'{hand_str} QTo UTG — fold.')
        if lo == 7 and is_suited and pos_idx >= 2:  # Q9s
            return r(f'{hand_str} 同花Q9，CO+开牌。', f'{hand_str} Q9s CO+ open.')
        return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')

    # ── J高 ──
    # JT=lo8, J9=lo7
    if hi == 9:
        if lo == 8:    # JT
            if is_suited or pos_idx >= 1:
                return r(f'{hand_str} {s}JT强连牌，HJ+开牌。',
                         f'{hand_str} {se}JT — strong connector, HJ+ open.')
            return f(f'{hand_str} JTo在UTG偏弱，弃牌。', f'{hand_str} JTo UTG — fold.')
        if lo == 7 and is_suited and pos_idx >= 2:  # J9s
            return r(f'{hand_str} 同花J9，CO+开牌。', f'{hand_str} J9s CO+ open.')
        return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')

    # ── 同花连牌 T9s-54s ──
    # T9s=lo7,98s=lo6,87s=lo5,76s=lo4,65s=lo3,54s=lo2
    if is_suited and gap <= 1:
        if lo >= 6:    # T9s(lo7), 98s(lo6) — HJ+
            if pos_idx >= 1:
                return r(f'{hand_str} 优质同花连牌，HJ+开牌。',
                         f'{hand_str} quality suited connector — HJ+ open.')
            return f(f'{hand_str} 同花连牌UTG偏弱，弃牌。',
                     f'{hand_str} suited connector too weak UTG — fold.')
        if lo >= 4:    # 87s(lo5), 76s(lo4) — CO+
            if pos_idx >= 2:
                return r(f'{hand_str} 同花连牌，CO+开牌。',
                         f'{hand_str} suited connector CO+ open.')
            return f(f'{hand_str} 弃牌。', f'{hand_str} fold.')
        if lo >= 2 and pos_idx >= 3:  # 65s(lo3), 54s(lo2) — BTN+
            return r(f'{hand_str} 小同花连牌，BTN+开牌。',
                     f'{hand_str} small suited connector BTN+ open.')

    return f(f'{hand_str} 不在开牌范围，弃牌。', f'{hand_str} outside opening range — fold.')


def _postflop_advice(hole_cards, board, street, pot, stack, opponent, villain_action):
    """
    翻后建议：综合考虑手牌强度、牌面纹理、对手行动线路、对手形象
    返回 (gto_action, gto_zh, gto_en, exploit_action, exploit_zh, exploit_en)
    """
    archetype = opponent.get('archetype', 'tag')
    stats     = opponent.get('stats', {})
    fold_cbet = stats.get('fold_to_cbet', 50)
    wtsd      = stats.get('wtsd', 28)
    agg       = stats.get('aggression', 2.0)
    vpip      = stats.get('vpip', 25)

    # ── 牌面分析 ──────────────────────────────────
    texture  = analyze_board(board)
    hbr      = hand_board_relation(hole_cards, board, texture)
    hand_rank = hbr['hand_rank']
    has_draw  = hbr['flush_draw'] or hbr['straight_draw']
    combo_draw = hbr['is_combo_draw']
    draw_outs  = hbr['draw_outs']
    strength   = hbr['hand_strength_vs_board']   # strong/moderate/vulnerable/weak/draw/air

    # 对手行动
    v_action  = villain_action.get('action', 'check') if villain_action else 'check'
    v_desc_zh = villain_action.get('desc_zh', '') if villain_action else ''
    v_desc_en = villain_action.get('desc_en', '') if villain_action else ''

    # ── GTO 建议（考虑牌面纹理）──────────────────
    if v_action == 'check':
        gto_a, gto_zh, gto_en = _gto_bet_or_check_v2(
            hand_rank, hbr, texture, street, pot, stack
        )
    else:
        gto_a, gto_zh, gto_en = _gto_facing_bet_v2(
            hand_rank, hbr, texture, street, pot, stack
        )

    # ── 剥削调整 ──────────────────────────────────
    exp_a, exp_zh, exp_en = gto_a, gto_zh, gto_en

    if v_action == 'check':
        # 对手弃牌太多：扩大半bluff范围
        if fold_cbet > 58 and gto_a == 'check' and draw_outs >= 6:
            exp_a  = 'bet'
            exp_zh = (f'GTO建议过牌，但对手Fold to Cbet={fold_cbet}%偏高。'
                      f'你有{draw_outs}张出牌，半bluff下注有正EV。'
                      f'{_texture_hint_zh(texture)}')
            exp_en = (f'GTO says check, but villain Fold to Cbet={fold_cbet}% is high. '
                      f'You have {draw_outs} outs — semi-bluff is profitable. '
                      f'{_texture_hint_en(texture)}')
        # 站型：弱牌不要下注bluff
        elif fold_cbet < 32 and gto_a == 'bet' and strength in ('weak', 'air'):
            exp_a  = 'check'
            exp_zh = (f'GTO建议下注，但对手Fold to Cbet={fold_cbet}%极低（站型特征）。'
                      f'对弱手牌下注是负EV的，选择过牌控制底池。')
            exp_en = (f'GTO says bet, but villain Fold to Cbet={fold_cbet}% is very low (calling station). '
                      f'Betting weak hands is -EV — check to control pot.')
        # 站型+强牌：大注获取价值
        elif wtsd > 38 and hand_rank >= 3:
            exp_zh = gto_zh + f' 对手WTSD={wtsd}%，喜欢走到摊牌，强牌应大注获取最大价值。'
            exp_en = gto_en + f' Villain WTSD={wtsd}% — goes to showdown often, bet large for maximum value.'
    else:
        # 对手是LAG：强牌加注
        if hand_rank >= 5 and archetype == 'lag':
            exp_a  = 'raise'
            exp_zh = (f'对手是LAG（攻击系数={agg}），{v_desc_zh}。'
                      f'你有强手牌，加注反击榨取最大价值。')
            exp_en = (f'Villain is LAG (aggression={agg}), {v_desc_en}. '
                      f'Strong hand — raise for maximum value.')
        # 对手是Nit：弱牌直接弃牌
        elif hand_rank <= 1 and not has_draw and archetype == 'nit':
            exp_a  = 'fold'
            exp_zh = (f'对手是Nit（VPIP={vpip}%），{v_desc_zh}。'
                      f'Nit下注几乎都是强牌，无强牌应弃牌。')
            exp_en = (f'Villain is Nit (VPIP={vpip}%), {v_desc_en}. '
                      f'Nit bets are almost always value — fold without a strong hand.')

    # 把对手行动和牌面信息加入建议
    texture_hint_zh = _texture_hint_zh(texture)
    texture_hint_en = _texture_hint_en(texture)
    if v_desc_zh and v_action != 'check':
        exp_zh = f'【{v_desc_zh}】 {exp_zh}'
        exp_en = f'[{v_desc_en}] {exp_en}'
    if texture_hint_zh and texture_hint_zh not in exp_zh:
        exp_zh = exp_zh + f' {texture_hint_zh}'
        exp_en = exp_en + f' {texture_hint_en}'

    return gto_a, gto_zh, gto_en, exp_a, exp_zh, exp_en


def _gto_bet_or_check_v2(hand_rank, hbr, texture, street, pot, stack):
    """
    对手check时，综合手牌强度+牌面纹理决定是否下注
    """
    strength   = hbr['hand_strength_vs_board']
    draw_outs  = hbr['draw_outs']
    is_wet     = texture['is_wet']
    is_dry     = texture['is_dry']
    danger     = texture['danger']
    combo_draw = hbr['is_combo_draw']
    flush_draw = hbr['flush_draw']
    straight_draw = hbr['straight_draw']
    is_overpair   = hbr['is_overpair']
    is_top_pair   = hbr['is_top_pair']

    # ── 极强手牌（满堂红+）──
    if hand_rank >= 6:
        return 'bet',             f'极强手牌（满堂红/四条以上），{_wet_dry_size_zh(is_wet, "large")}建底池。',             f'Monster hand (full house+) — {_wet_dry_size_en(is_wet, "large")} to build pot.'

    # ── 同花 ──
    if hand_rank == 5:
        if is_wet:
            return 'bet',                 f'同花在湿润牌面应立即下注，防止对手免费完成更强的同花或顺子。选择中大注。',                 f'Flush on a wet board — bet medium-large immediately to deny free draws.'
        return 'bet',             f'同花在干燥牌面，中注建底池获取价值，慢玩风险低但错过价值。',             f'Flush on a dry board — bet medium for value (slow play risk is low but missed value).'

    # ── 顺子 ──
    if hand_rank == 4:
        if texture['flush_texture'] in ('two_tone', 'monotone', 'flush_draw'):
            return 'bet',                 f'顺子在有同花可能的牌面，必须立即大注建底池，防止对手免费完成同花反超你。',                 f'Straight on a flush-possible board — bet large immediately, deny flush draw.'
        if texture['connectivity'] == 'very_connected':
            return 'bet',                 f'顺子在高度连牌面，注意可能有更高顺子。中注建底池并收集信息。',                 f'Straight on a very connected board — bet medium, watch for higher straights.'
        return 'bet',             f'顺子在干燥牌面，大注建底池，对手很难有更强手牌。',             f'Straight on a dry board — bet large, opponent unlikely to have better.'

    # ── 三条 ──
    if hand_rank == 3:
        if is_wet:
            return 'bet',                 f'三条在湿润牌面必须下注，防止对手免费完成顺子或同花。选择中大注（50-75%）。',                 f'Trips on a wet board — must bet (50-75%) to deny draws, protect your hand.'
        return 'bet',             f'三条在干燥牌面有时可以慢玩，但中注建底池更稳妥。',             f'Trips on a dry board — can slow play occasionally, but betting medium is safer.'

    # ── 两对 ──
    if hand_rank == 2:
        if danger >= 6:
            return 'bet',                 f'两对在危险牌面（danger={danger}）必须下注保护，防止对手免费看牌完成听牌。大注施压。',                 f'Two pair on a dangerous board (danger={danger}) — bet large to protect, deny draws.'
        if danger >= 4:
            return 'bet',                 f'两对在半湿牌面，中注建底池同时保护手牌。',                 f'Two pair on a semi-wet board — bet medium to build pot and protect.'
        return 'bet',             f'两对在干燥牌面有价值，中小注建底池。',             f'Two pair on a dry board — bet small-medium for value.'

    # ── 一对 ──
    if hand_rank == 1:
        if is_overpair:
            if danger >= 7:
                return 'bet',                     f'超对在极湿牌面（danger={danger}）必须小注保护，不要给对手免费看牌机会。',                     f'Overpair on a very wet board (danger={danger}) — bet small to protect, no free cards.'
            if danger >= 4:
                return 'bet',                     f'超对在湿润牌面，小注收集信息同时建底池。对手有大量听牌需要付出代价。',                     f'Overpair on a wet board — bet small to charge draws and gather info.'
            return 'bet',                 f'超对在干燥牌面，中注建底池，优势明显。',                 f'Overpair on a dry board — bet medium, you have clear advantage.'
        if is_top_pair:
            if danger >= 6:
                return 'check',                     f'顶对在湿润危险牌面（danger={danger}），建议过牌控制底池，避免在劣势时损失过多。',                     f'Top pair on a wet/dangerous board (danger={danger}) — check to control pot size.'
            return 'bet',                 f'顶对在合理牌面，小注建底池收集信息。',                 f'Top pair on a reasonable board — bet small to build pot and gather information.'
        # 中下对子
        return 'check',             f'中下对子强度不足，建议过牌控制底池。等待转牌再评估。',             f'Middle/bottom pair — check to control pot. Reassess on the turn.'

    # ── 无成牌：听牌/半bluff/过牌 ──
    if combo_draw:
        return 'bet',             f'Combo draw（同花+顺子双重听牌），约{draw_outs}张出牌，权益超55%。大注半bluff，即使被跟注也有大量出牌。',             f'Combo draw ({draw_outs} outs, 55%+ equity) — large semi-bluff. Even if called, you have massive equity.'
    if flush_draw:
        if is_wet:
            return 'bet',                 f'同花听牌（{draw_outs}张出牌≈35%权益）在湿润牌面，半bluff中注施压。牌面有利于你的范围。',                 f'Flush draw ({draw_outs} outs ≈35%) on wet board — semi-bluff medium. Board favors your range.'
        return 'bet',             f'同花听牌（{draw_outs}张出牌≈35%权益），半bluff小中注施压。',             f'Flush draw ({draw_outs} outs ≈35%) — semi-bluff small-medium.'
    if straight_draw:
        if is_wet:
            return 'bet',                 f'顺子听牌（{draw_outs}张出牌≈30%权益）在连牌面，半bluff施压合理。',                 f'Straight draw ({draw_outs} outs ≈30%) on connected board — semi-bluff reasonable.'
        if danger <= 2:
            return 'check',                 f'顺子听牌在干燥牌面，过牌免费看转牌的EV更高（被跟注的风险更大）。',                 f'Straight draw on a dry board — checking has higher EV (risk of being raised).'
        return 'bet',             f'顺子听牌（{draw_outs}张出牌≈30%权益），小注半bluff。',             f'Straight draw ({draw_outs} outs ≈30%) — small semi-bluff.'

    # 完全空气牌
    if is_wet and texture['high_card'] in ('ace_high', 'king_high'):
        return 'bet',             f'无成牌在A/K高湿润牌面，你的范围有优势（有更多AK/AQ等），可以用范围优势c-bet小注。',             f'Air on A/K high wet board — your range advantage (AK/AQ etc) justifies a small range c-bet.'
    return 'check',         f'无成牌也无听牌，过牌。等待好牌或对手主动下注再决策。',         f'No made hand, no draw — check. Wait for a good card or let opponent bet.'


def _gto_facing_bet_v2(hand_rank, hbr, texture, street, pot, stack):
    """
    面对对手下注时的建议（考虑牌面纹理）
    """
    strength   = hbr['hand_strength_vs_board']
    has_draw   = hbr['flush_draw'] or hbr['straight_draw']
    combo_draw = hbr['is_combo_draw']
    draw_outs  = hbr['draw_outs']
    danger     = texture['danger']
    is_wet     = texture['is_wet']

    needed = round(pot_odds(pot, pot * 0.6)['needed_equity'], 1)

    if hand_rank >= 6:
        return 'raise',             f'极强手牌（满堂红/四条以上），加注全押获取最大价值。',             f'Monster hand — raise/all-in for maximum value.'

    if hand_rank == 5:
        if is_wet:
            return 'raise',                 f'同花在湿润牌面，立即加注建更大底池，不给对手免费完成更强同花的机会。',                 f'Flush on a wet board — raise to build a big pot, deny stronger flush draws.'
        return 'raise',             f'同花是强手牌，加注获取最大价值。',             f'Flush — raise for maximum value.'

    if hand_rank == 4:
        if texture['flush_texture'] in ('two_tone', 'flush_draw', 'monotone'):
            return 'raise',                 f'顺子面对下注，但牌面有同花可能，加注立即建大底池，不要让对手免费完成同花。',                 f'Straight facing a bet — flush draw possible, raise to build pot and deny draws.'
        return 'raise',             f'顺子是强手牌，加注获取价值。',             f'Straight — raise for value.'

    if hand_rank == 3:
        if is_wet:
            return 'raise',                 f'三条在湿润牌面，加注保护手牌同时建底池，不要给对手免费完成顺子或同花。',                 f'Trips on a wet board — raise to protect and build pot, deny draws.'
        return 'call',             f'三条在干燥牌面，跟注慢玩，等待转牌再建大底池。',             f'Trips on a dry board — call/slow play, build bigger pot on the turn.'

    if hand_rank == 2:
        if danger >= 7:
            return 'call',                 f'两对在极危险牌面（danger={danger}），跟注谨慎，不要在被超越的可能性很高时投入过多。',                 f'Two pair on a very dangerous board (danger={danger}) — call cautiously.'
        return 'call',             f'两对跟注，建底池。注意后续公共牌是否改变局面。',             f'Two pair — call to build pot. Watch for board changes.'

    if hand_rank == 1:
        if strength == 'vulnerable' and danger >= 6:
            return 'fold',                 f'一对在极湿润危险牌面（danger={danger}）面对下注，强度太弱，建议弃牌。',                 f'One pair on a very wet/dangerous board (danger={danger}) — too weak, fold.'
        if hbr['is_overpair'] or hbr['is_top_pair']:
            return 'call',                 f'{"超对" if hbr["is_overpair"] else "顶对"}跟注，评估底池赔率。需要约{needed}%权益（你的一对约35-45%）。',                 f'{"Overpair" if hbr["is_overpair"] else "Top pair"} — call, need ~{needed}% equity (one pair ≈35-45%).'
        return 'fold',             f'中下对子面对下注，赔率不合算（需要{needed}%，一对通常约25-35%权益），弃牌。',             f'Middle/bottom pair — pot odds require {needed}% equity (pair has ≈25-35%), fold.'

    if combo_draw:
        return 'raise',             f'Combo draw（{draw_outs}张出牌，权益55%+），已经是翻牌领先！加注建最大底池。',             f'Combo draw ({draw_outs} outs, 55%+ equity) — you are ahead! Raise to build maximum pot.'

    if has_draw:
        eq_approx = round(draw_outs * 2, 0)  # 单街权益估算
        if draw_outs >= 9:   # 同花听牌
            return 'call',                 f'同花听牌（{draw_outs}张出牌≈{eq_approx}%单街权益），底池赔率合算跟注。需要{needed}%，你有约{eq_approx}%。',                 f'Flush draw ({draw_outs} outs ≈{eq_approx}% per street) — pot odds justify a call. Need {needed}%, you have ≈{eq_approx}%.'
        if draw_outs >= 6:
            return 'call',                 f'顺子听牌（{draw_outs}张出牌≈{eq_approx}%单街权益），如果赔率合算可以跟注。需要{needed}%，你有约{eq_approx}%。',                 f'Straight draw ({draw_outs} outs ≈{eq_approx}% per street) — call if pot odds are right. Need {needed}%, have ≈{eq_approx}%.'
        return 'fold',             f'弱听牌（{draw_outs}张出牌≈{eq_approx}%权益），赔率不合算，弃牌。需要{needed}%。',             f'Weak draw ({draw_outs} outs ≈{eq_approx}%) — pot odds do not justify a call (need {needed}%), fold.'

    return 'fold',         f'无成牌也无听牌，面对下注直接弃牌。',         f'No made hand, no draw — fold to the bet.'


def _wet_dry_size_zh(is_wet, size):
    if size == 'large':
        return '大注（75%+）' if is_wet else '中大注（50-75%）'
    return '中注（50%）' if is_wet else '小注（33-50%）'

def _wet_dry_size_en(is_wet, size):
    if size == 'large':
        return 'large bet (75%+)' if is_wet else 'medium-large bet (50-75%)'
    return 'medium bet (50%)' if is_wet else 'small bet (33-50%)'

def _texture_hint_zh(t):
    parts = []
    if t['flush_texture'] == 'monotone':
        parts.append('单色牌面威胁极大，注意对手可能有同花。')
    elif t['flush_texture'] == 'two_tone':
        parts.append('双色牌面有同花听牌，需要让对手付出代价。')
    if t['connectivity'] == 'very_connected':
        parts.append('高度连牌面，对手有大量顺子/听牌可能。')
    elif t['connectivity'] == 'connected':
        parts.append('连牌面，注意顺子可能。')
    if t['pair_structure'] == 'paired':
        parts.append('配对牌面，听牌变少但三条/葫芦可能性增加。')
    return ' '.join(parts)

def _texture_hint_en(t):
    parts = []
    if t['flush_texture'] == 'monotone':
        parts.append('Monotone board — opponent may have a flush.')
    elif t['flush_texture'] == 'two_tone':
        parts.append('Two-tone board — flush draw possible, charge draws.')
    if t['connectivity'] == 'very_connected':
        parts.append('Very connected board — many straight/draw possibilities.')
    elif t['connectivity'] == 'connected':
        parts.append('Connected board — watch for straights.')
    if t['pair_structure'] == 'paired':
        parts.append('Paired board — fewer draws but trips/boats more likely.')
    return ' '.join(parts)


# ── 工具函数 ──────────────────────────────────────────────

def calc_sizing(pot: float, stack: float, villain_action: dict = None) -> dict:
    """
    计算当前街的下注尺度信息：
    - 对手下注了多少（如果有）
    - 你下注各种尺度的具体金额
    - 底池赔率（如果对手下注）
    - 建议下注尺度
    """
    sizing = {
        'pot':          round(pot, 1),
        'stack':        round(stack, 1),
        'bet_33':       round(pot * 0.33, 1),
        'bet_50':       round(pot * 0.50, 1),
        'bet_75':       round(pot * 0.75, 1),
        'bet_100':      round(pot * 1.00, 1),
        'villain_bet':  None,
        'pot_odds':     None,
        'needed_equity':None,
    }

    if villain_action and villain_action.get('action') in ['bet', 'raise']:
        # 对手的下注额（根据对手形象模拟一个合理尺度）
        vbet = round(pot * random.uniform(0.45, 0.75), 1)
        sizing['villain_bet'] = vbet
        # 底池赔率
        total_pot = pot + vbet + vbet  # pot + villain bet + hero call
        needed_eq = round(vbet / total_pot * 100, 1)
        sizing['pot_odds']      = round((pot + vbet) / vbet, 2)
        sizing['needed_equity'] = needed_eq
        sizing['call_amount']   = vbet

    return sizing


def _normalize(action: str) -> str:
    """归一化行动类别，用于判断对错"""
    if action in ['bet', 'bet_large', 'bet_medium', 'bet_small', 'raise', '3bet', '4bet']:
        return 'aggressive'
    if action == 'call':
        return 'call'
    if action == 'check':
        return 'check'
    return 'fold'


def _next_street(current: str) -> Optional[str]:
    idx = STREETS.index(current)
    return STREETS[idx + 1] if idx < len(STREETS) - 1 else None


def _update_pot(hand: HandState, action: str, street: str):
    """根据行动更新底池和筹码"""
    if street == 'preflop':
        if action in ['raise', '3bet', '4bet']:
            raise_size = round(hand.pot * 2.5, 1)
            hand.pot  += raise_size
            hand.stack = max(0, hand.stack - raise_size)
        elif action == 'call':
            hand.pot  += 2.0
            hand.stack = max(0, hand.stack - 2.0)
    else:
        bet = round(hand.pot * 0.6, 1)
        if action in ['bet', 'raise']:
            hand.pot  += bet * 2
            hand.stack = max(0, hand.stack - bet)
        elif action == 'call':
            hand.pot  += bet
            hand.stack = max(0, hand.stack - bet)


def _quick_equity(hole_cards, board) -> Optional[float]:
    """快速权益估算（少量模拟，不阻塞响应）"""
    try:
        result = calc_equity(hole_cards, None, board, simulations=600)
        return result['hero']
    except Exception:
        return None


def _is_top_pair(board) -> bool:
    """判断是否有顶对（最高牌面）"""
    if not board:
        return False
    top = max(c.val for c in board)
    return True  # 简化：只要有对子就算顶对判断
