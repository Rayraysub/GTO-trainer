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

    # 手牌强度评分
    hand_rank = best_hand_from_7(hole_cards, board)[0] if board else 0
    flush_draw    = _has_flush_draw(hole_cards, board) if board else False
    straight_draw = _has_straight_draw(hole_cards, board) if board else False
    has_draw      = flush_draw or straight_draw
    combo_draw    = flush_draw and straight_draw

    # 对手行动
    v_action = villain_action.get('action', 'check') if villain_action else 'check'
    v_desc_zh = villain_action.get('desc_zh', '') if villain_action else ''
    v_desc_en = villain_action.get('desc_en', '') if villain_action else ''

    # ── GTO 建议 ──
    if v_action == 'check':
        gto_a, gto_zh, gto_en = _gto_bet_or_check(
            hand_rank, has_draw, combo_draw, flush_draw, straight_draw,
            board, street, pot, stack
        )
    else:  # 对手下注，需要决定 call/raise/fold
        gto_a, gto_zh, gto_en = _gto_facing_bet(
            hand_rank, has_draw, combo_draw, board, street, pot, stack
        )

    # ── 剥削调整 ──
    exp_a   = gto_a
    exp_zh  = gto_zh
    exp_en  = gto_en

    if v_action == 'check':
        # 对手check，考虑是否下注
        if fold_cbet > 58 and gto_a == 'check' and (has_draw or hand_rank == 0):
            exp_a   = 'bet'
            exp_zh  = f'GTO建议过牌，但对手Fold to Cbet={fold_cbet}%（偏高）。{v_desc_zh}，可以半bluff下注。'
            exp_en  = f'GTO says check, but villain Fold to Cbet={fold_cbet}% (high). {v_desc_en} — semi-bluff bet profitable.'
        elif fold_cbet < 35 and gto_a == 'bet' and hand_rank <= 1:
            exp_a   = 'check'
            exp_zh  = f'GTO建议下注，但对手Fold to Cbet={fold_cbet}%（很低，站型特征）。{v_desc_zh}，弱牌下注无效，选择过牌。'
            exp_en  = f'GTO says bet, but villain Fold to Cbet={fold_cbet}% (very low — calling station). {v_desc_en} — bluffing wastes money, check.'
        elif hand_rank >= 3 and wtsd > 38:
            exp_zh  = f'{gto_zh} 对手WTSD={wtsd}%（喜欢走到摊牌），有强牌时大注获取价值。'
            exp_en  = f'{gto_en} Villain WTSD={wtsd}% (goes to showdown often) — bet big for value with strong hands.'
    else:
        # 对手下注
        if hand_rank >= 5 and archetype == 'lag':
            exp_a   = 'raise'
            exp_zh  = f'对手是LAG（攻击系数={agg}），{v_desc_zh}。你有强牌，加注反击可以获取更多价值。'
            exp_en  = f'Villain is LAG (aggression={agg}), {v_desc_en}. You have a strong hand — raise for max value.'
        elif hand_rank <= 1 and not has_draw and archetype == 'nit':
            exp_a   = 'fold'
            exp_zh  = f'对手是Nit（VPIP={stats.get("vpip", 12)}%），{v_desc_zh}，Nit下注几乎都是强牌，弱牌弃牌。'
            exp_en  = f'Villain is Nit (VPIP={stats.get("vpip", 12)}%), {v_desc_en} — Nit bets are almost always value, fold weak hands.'

    # 把对手行动纳入建议文字
    if v_desc_zh and v_action != 'check':
        exp_zh = f'【{v_desc_zh}】 ' + exp_zh
        exp_en = f'[{v_desc_en}] ' + exp_en

    return gto_a, gto_zh, gto_en, exp_a, exp_zh, exp_en


def _gto_bet_or_check(hand_rank, has_draw, combo_draw, flush_draw,
                       straight_draw, board, street, pot, stack):
    """对手check时，我们是否下注？"""
    if hand_rank >= 6:
        return 'bet', \
            f'持有极强手牌（满堂红/四条以上），大注建底池获取最大价值。', \
            f'Extremely strong hand (full house+) — bet large to build the pot.'
    if hand_rank == 5:
        return 'bet', \
            f'同花是强手牌，中大注建底池，同时防止对手免费看牌。', \
            f'Flush is a strong hand — bet medium-large to build pot and deny free cards.'
    if hand_rank == 4:
        return 'bet', \
            f'顺子是强手牌，中注建底池。注意是否有更高顺子可能。', \
            f'Straight is strong — bet medium. Watch for higher straight possibilities.'
    if hand_rank == 3:
        return 'bet', \
            f'三条有足够强度下注建底池，不要慢玩让对手免费完成听牌。', \
            f'Trips — bet to build the pot and deny free draws.'
    if hand_rank == 2:
        return 'bet', \
            f'两对有价值，中注建底池。注意河牌是否会被超越。', \
            f'Two pair — bet for value. Watch out for river cards that beat you.'
    if hand_rank == 1:
        top_pair = _is_top_pair(board)
        if top_pair:
            return 'bet', \
                f'顶对有足够强度小注建底池，同时收集信息。', \
                f'Top pair — bet small to build pot and gather information.'
        return 'check', \
            f'中下对子强度不足，过牌控制底池。', \
            f'Middle/bottom pair — check to control pot size.'
    # 高牌/无成牌
    if combo_draw:
        return 'bet', \
            f'Combo draw（顺子+同花听牌）权益超55%，半bluff大注。', \
            f'Combo draw (straight + flush) has 55%+ equity — large semi-bluff.'
    if flush_draw:
        return 'bet', \
            f'同花听牌约35%权益，半bluff中注施压。', \
            f'Flush draw ~35% equity — medium semi-bluff.'
    if straight_draw:
        return 'bet', \
            f'顺子听牌约30%权益，可以小注半bluff。', \
            f'Straight draw ~30% equity — small semi-bluff.'
    return 'check', \
        f'无成牌也无听牌，过牌。等待好的出牌或免费看牌机会。', \
        f'No made hand, no draw — check. Wait for a good card or free look.'


def _gto_facing_bet(hand_rank, has_draw, combo_draw, board, street, pot, stack):
    """面对对手下注时的建议"""
    if hand_rank >= 5:
        return 'raise', \
            f'持有强手牌（同花/顺子以上），加注反击获取最大价值。', \
            f'Strong hand (flush+) — raise for maximum value.'
    if hand_rank >= 3:
        return 'call', \
            f'三条/两对强度足够跟注，等待进一步建底池机会。', \
            f'Trips/two pair — call and look for more value later.'
    if hand_rank == 2:
        return 'call', \
            f'两对跟注，但注意后续公共牌是否会被超越。', \
            f'Two pair — call, but watch for overcards on later streets.'
    if hand_rank == 1:
        needed = pot_odds(pot, pot * 0.5)['needed_equity']
        return 'call', \
            f'单对跟注，需要约{needed}%权益。评估是否有足够隐含赔率。', \
            f'One pair — call requires ~{needed}% equity. Assess implied odds.'
    if combo_draw:
        return 'raise', \
            f'Combo draw权益超55%，半bluff加注或跟注均可，加注可以赢更多底池。', \
            f'Combo draw 55%+ equity — raise or call; raising wins a bigger pot.'
    if has_draw:
        needed = pot_odds(pot, pot * 0.6)['needed_equity']
        return 'call', \
            f'听牌跟注，权益约30-35%，确认赔率合算再跟注。需要约{needed}%。', \
            f'Draw — call if pot odds justify it. Need ~{needed}% equity.'
    return 'fold', \
        f'无强牌也无听牌，面对下注应弃牌。', \
        f'No made hand and no draw — fold to the bet.'


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
