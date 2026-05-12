"""
poker_engine.py
---------------
核心扑克逻辑：发牌、手牌评估、权益计算（蒙特卡洛模拟）
"""

import random
import itertools
from collections import Counter

# ── 基础常量 ──────────────────────────────────────────────
RANKS = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
SUITS = ['s','h','d','c']          # spade heart diamond club
RANK_VAL = {r: i for i, r in enumerate(RANKS)}  # '2'=0 … 'A'=12

SUIT_SYMBOLS = {'s':'♠', 'h':'♥', 'd':'♦', 'c':'♣'}
SUIT_COLORS  = {'s':'black', 'h':'red', 'd':'red', 'c':'black'}

# ── Card & Deck ───────────────────────────────────────────
class Card:
    def __init__(self, rank: str, suit: str):
        self.rank = rank.upper() if rank in ['t','j','q','k','a'] else rank
        self.rank = self.rank if self.rank in RANKS else rank.upper()
        self.suit = suit.lower()
        self.val  = RANK_VAL[self.rank]

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def to_dict(self):
        return {
            'rank': self.rank,
            'suit': self.suit,
            'symbol': SUIT_SYMBOLS[self.suit],
            'color':  SUIT_COLORS[self.suit],
            'str':    f"{self.rank}{SUIT_SYMBOLS[self.suit]}"
        }

    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self):
        return hash((self.rank, self.suit))


class Deck:
    def __init__(self):
        self.cards = [Card(r, s) for r in RANKS for s in SUITS]
        self.shuffled = False

    def shuffle(self):
        random.shuffle(self.cards)
        self.shuffled = True
        return self

    def remove(self, cards):
        """从牌堆移除指定牌（已知牌面）"""
        card_set = {str(c) for c in cards}
        self.cards = [c for c in self.cards if str(c) not in card_set]
        return self

    def deal(self, n=1):
        if not self.shuffled:
            self.shuffle()
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt

    def remaining(self):
        return len(self.cards)


# ── Hand Evaluator (简化7牌评估) ──────────────────────────
HAND_RANKS = {
    'high_card':0, 'one_pair':1, 'two_pair':2,
    'three_of_a_kind':3, 'straight':4, 'flush':5,
    'full_house':6, 'four_of_a_kind':7, 'straight_flush':8, 'royal_flush':9
}

def evaluate_5(cards):
    """
    评估5张牌，返回 (hand_rank, tiebreak_tuple)
    hand_rank越大越强
    """
    vals  = sorted([c.val for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    ranks = [c.rank for c in cards]

    is_flush    = len(set(suits)) == 1
    sorted_vals = sorted(vals)
    is_straight = (sorted_vals == list(range(sorted_vals[0], sorted_vals[0]+5)))
    # A-2-3-4-5 wheel straight
    is_wheel    = sorted_vals == [0,1,2,3,12]

    counts = Counter(vals)
    freq   = sorted(counts.values(), reverse=True)
    groups = sorted(counts.keys(), key=lambda x: (counts[x], x), reverse=True)

    if is_flush and is_straight:
        if vals[0] == 12 and vals[1] == 11:
            return (HAND_RANKS['royal_flush'], tuple(vals))
        return (HAND_RANKS['straight_flush'], tuple(vals))
    if freq[0] == 4:
        return (HAND_RANKS['four_of_a_kind'], tuple(groups))
    if freq[:2] == [3,2]:
        return (HAND_RANKS['full_house'], tuple(groups))
    if is_flush:
        return (HAND_RANKS['flush'], tuple(vals))
    if is_straight or is_wheel:
        top = 3 if is_wheel else vals[0]
        return (HAND_RANKS['straight'], (top,))
    if freq[0] == 3:
        return (HAND_RANKS['three_of_a_kind'], tuple(groups))
    if freq[:2] == [2,2]:
        return (HAND_RANKS['two_pair'], tuple(groups))
    if freq[0] == 2:
        return (HAND_RANKS['one_pair'], tuple(groups))
    return (HAND_RANKS['high_card'], tuple(vals))


def best_hand_from_7(hole_cards, board_cards):
    """从 2 张底牌 + 最多 5 张公共牌中找最强5张"""
    all_cards = hole_cards + board_cards
    best = None
    for combo in itertools.combinations(all_cards, 5):
        score = evaluate_5(list(combo))
        if best is None or score > best:
            best = score
    return best


# ── 蒙特卡洛权益计算 ──────────────────────────────────────
def calc_equity(hero_hole, villain_hole, board=None, simulations=5000):
    """
    hero_hole   : [Card, Card]
    villain_hole: [Card, Card] 或 None（随机对手范围）
    board       : [Card, ...] 0-5张，None表示翻前
    simulations : 模拟次数
    返回 {'hero': float, 'villain': float, 'tie': float}
    """
    board = board or []
    known = set(str(c) for c in hero_hole + (villain_hole or []) + board)

    wins, losses, ties = 0, 0, 0

    for _ in range(simulations):
        deck = Deck()
        deck.shuffle()
        deck.remove([c for c in hero_hole + (villain_hole or []) + board])

        remaining_board = deck.deal(5 - len(board))
        full_board = board + remaining_board

        if villain_hole is None:
            vill = deck.deal(2)
        else:
            vill = villain_hole

        hero_score = best_hand_from_7(hero_hole, full_board)
        vill_score = best_hand_from_7(vill,      full_board)

        if hero_score > vill_score:
            wins += 1
        elif vill_score > hero_score:
            losses += 1
        else:
            ties += 1

    total = simulations
    return {
        'hero':    round(wins   / total * 100, 1),
        'villain': round(losses / total * 100, 1),
        'tie':     round(ties   / total * 100, 1),
        'simulations': simulations
    }


# ── 底池赔率 & EV ────────────────────────────────────────
def pot_odds(pot: float, bet: float) -> dict:
    """计算底池赔率"""
    call_amt   = bet
    total_pot  = pot + bet + call_amt
    needed_eq  = call_amt / total_pot * 100
    ratio      = (pot + bet) / call_amt
    bet_pct    = bet / pot * 100
    return {
        'needed_equity': round(needed_eq, 1),
        'pot_odds_ratio': round(ratio, 2),
        'bet_pct_of_pot': round(bet_pct, 1),
        'call_amount': call_amt,
        'total_pot': round(total_pot, 1)
    }


def calc_ev(pot: float, bet: float, fold_pct: float, equity_pct: float) -> dict:
    """计算下注EV"""
    fp  = fold_pct  / 100
    cp  = 1 - fp
    eq  = equity_pct / 100

    ev_bet   = fp * pot + cp * ((pot + bet * 2) * eq - bet)
    ev_check = eq * pot
    ev_fold  = 0.0

    best = max(ev_bet, ev_check, ev_fold)
    if best == ev_bet:   best_action = 'bet'
    elif best == ev_check: best_action = 'check'
    else:                  best_action = 'fold'

    gto_fold_rate = bet / (pot + bet) * 100

    return {
        'ev_bet':        round(ev_bet,   2),
        'ev_check':      round(ev_check, 2),
        'ev_fold':       0.0,
        'best_action':   best_action,
        'gto_fold_rate': round(gto_fold_rate, 1)
    }


# ── 随机场景生成器 ────────────────────────────────────────
POSITIONS_6MAX = ['UTG','HJ','CO','BTN','SB','BB']

def random_scenario(street: str = None, position: str = None) -> dict:
    """
    生成一个随机训练场景：
    - 随机手牌
    - 随机位置
    - 随机牌面（根据street）
    - 基于简单GTO规则给出建议行动
    """
    deck = Deck().shuffle()

    # 随机位置
    hero_pos = position or random.choice(POSITIONS_6MAX)
    villain_pos = random.choice([p for p in POSITIONS_6MAX if p != hero_pos])

    # 随机手牌
    hole = deck.deal(2)

    # 随机街道
    if street is None:
        street = random.choice(['preflop','flop','turn','river'])

    # 随机牌面
    board = []
    if street in ['flop','turn','river']:
        board = deck.deal(3)
    if street in ['turn','river']:
        board += deck.deal(1)
    if street == 'river':
        board += deck.deal(1)

    # 随机底池和筹码
    pot   = round(random.choice([4, 5.5, 8, 12, 18, 25, 40, 60, 80, 100]), 1)
    stack = round(random.uniform(40, 150), 0)

    # 简单GTO建议
    gto_action, gto_reason = simple_gto_advice(hole, board, street, hero_pos, pot, stack)

    return {
        'street':       street,
        'hero_pos':     hero_pos,
        'villain_pos':  villain_pos,
        'hole_cards':   [c.to_dict() for c in hole],
        'board':        [c.to_dict() for c in board],
        'pot':          pot,
        'stack':        stack,
        'gto_action':   gto_action,
        'gto_reason':   gto_reason,
        'hand_str':     classify_hole(hole),
    }


def classify_hole(hole):
    """将手牌分类为字符串，如 AKs, TT, 72o"""
    r1, r2 = hole[0], hole[1]
    if r1.val < r2.val:
        r1, r2 = r2, r1
    if r1.rank == r2.rank:
        return r1.rank + r2.rank
    suited = 's' if r1.suit == r2.suit else 'o'
    return r1.rank + r2.rank + suited


def simple_gto_advice(hole, board, street, position, pot, stack):
    """
    基于简化GTO规则给出建议行动和理由
    （完整GTO需要PioSOLVER，这里是规则近似）
    """
    hand_str = classify_hole(hole)
    r1, r2 = (hole[0], hole[1]) if hole[0].val >= hole[1].val else (hole[1], hole[0])
    is_pair  = r1.rank == r2.rank
    is_suited = r1.suit == r2.suit
    hi_val   = r1.val   # 0-12
    lo_val   = r2.val
    gap      = hi_val - lo_val

    if street == 'preflop':
        return _preflop_advice(hand_str, is_pair, is_suited, hi_val, lo_val, gap, position)
    elif street == 'flop':
        return _postflop_advice(hole, board, 'flop', pot, stack)
    elif street == 'turn':
        return _postflop_advice(hole, board, 'turn', pot, stack)
    else:
        return _postflop_advice(hole, board, 'river', pot, stack)


def _preflop_advice(hand_str, is_pair, is_suited, hi_val, lo_val, gap, position):
    pos_idx = POSITIONS_6MAX.index(position)  # 0=UTG, 5=BB

    # 对子
    if is_pair:
        pair_val = hi_val
        if pair_val >= 10:   # TT+
            return 'raise', f'{hand_str} 是强对子，任何位置均应加注建底池。'
        if pair_val >= 6:    # 66-99
            if pos_idx >= 3: # CO/BTN/SB
                return 'raise', f'{hand_str} 在后位有足够价值开牌，同时有隐含赔率Set。'
            return 'raise', f'{hand_str} 在中早位可以开牌，期待Set隐含赔率。'
        # 22-55
        if pos_idx >= 3:
            return 'raise', f'{hand_str} 小对子在后位可以开牌，主要价值来自Set。'
        if pos_idx <= 1:
            return 'fold', f'{hand_str} 小对子在早位开牌范围之外，应弃牌。'
        return 'raise', f'{hand_str} 中位可以开牌，Set价值足够。'

    # 非对子
    if hi_val == 12:  # A high
        if lo_val >= 11:  # AK
            return 'raise', f'{hand_str} 是顶级手牌，任何位置纯加注。'
        if lo_val >= 9:   # AQ, AJ, AT
            if is_suited or pos_idx >= 2:
                return 'raise', f'{hand_str} {"同花" if is_suited else ""}在此位置有足够权益加注。'
            return 'raise', f'{hand_str} 在CO+应标准加注。'
        if lo_val >= 4 and is_suited:  # A5s-A8s
            if pos_idx >= 3:
                return 'raise', f'{hand_str} 同花A在后位是标准加注，有轮子顺子潜力。'
            return 'fold', f'{hand_str} 在早中位权益不足，应弃牌。'
        return 'fold', f'{hand_str} 权益不足，在此位置应弃牌。'

    # 连牌同花
    if is_suited and gap <= 1 and lo_val >= 6:
        if pos_idx >= 2:
            return 'raise', f'{hand_str} 同花连牌在后位有良好可玩性，标准加注。'
        if lo_val >= 9:
            return 'raise', f'{hand_str} 高同花连牌在早位也在开牌范围。'
        return 'fold', f'{hand_str} 在早位可玩性不够，范围外弃牌。'

    # 高牌组合
    if hi_val >= 11 and lo_val >= 10:  # KQ, KJ, QJ
        if pos_idx >= 2 or is_suited:
            return 'raise', f'{hand_str} 在此位置权益足够，标准加注。'
        return 'fold', f'{hand_str} 在早位过早，应弃牌。'

    return 'fold', f'{hand_str} 不在此位置的开牌范围，应弃牌。'


def _postflop_advice(hole, board, street, pot, stack):
    """翻后简化建议，基于手牌强度分级"""
    from poker_engine import best_hand_from_7
    score = best_hand_from_7(hole, board)
    rank  = score[0]

    # 手牌强度分级
    if rank >= 6:   # full house+
        action = 'bet_large'
        reason = f'你持有极强的手牌（满堂红/四条/同花顺），应大注建底池获取最大价值。'
    elif rank == 5: # flush
        action = 'bet_large'
        reason = '同花是强手牌，应积极下注获取价值，同时防止对手免费看牌。'
    elif rank == 4: # straight
        action = 'bet_medium'
        reason = '顺子是强手牌，应中大注建底池，注意是否有更高顺子可能。'
    elif rank == 3: # trips
        action = 'bet_medium'
        reason = '三条是强手牌，建议中注建底池，不要过快吓跑对手。'
    elif rank == 2: # two pair
        if street == 'river':
            action = 'bet_medium'
            reason = '两对在河牌是强牌，中注获取价值，注意是否被顺子/同花超越。'
        else:
            action = 'bet_medium'
            reason = '两对有足够强度下注建底池，同时保护手牌防止对手免费看牌。'
    elif rank == 1: # one pair
        hi_pair = score[1][0]
        if hi_pair >= 10:  # 顶对或超对
            action = 'bet_small'
            reason = '强对子应小注建底池，同时收集信息。'
        else:
            action = 'check'
            reason = '中弱对子建议过牌控制底池，避免在劣势时损失更多。'
    else:  # high card
        # 判断是否有听牌
        flush_draw = _has_flush_draw(hole, board)
        straight_draw = _has_straight_draw(hole, board)
        if flush_draw and straight_draw:
            action = 'bet_large'
            reason = 'Combo draw（顺子+同花听牌）权益超50%，应半bluff大注。'
        elif flush_draw:
            action = 'bet_medium'
            reason = '同花听牌约35%权益，半bluff中注合适。'
        elif straight_draw:
            action = 'bet_small'
            reason = '顺子听牌约30%权益，可以小注半bluff。'
        else:
            action = 'check'
            reason = '高牌没有强度也没有听牌，建议过牌。'

    # 将行动转为具体建议
    action_map = {
        'bet_large':  ('bet', '75%底池', round(pot * 0.75, 1)),
        'bet_medium': ('bet', '50%底池', round(pot * 0.5,  1)),
        'bet_small':  ('bet', '33%底池', round(pot * 0.33, 1)),
        'check':      ('check', '', 0),
    }
    act, sizing, amount = action_map[action]
    return act, reason


def _has_flush_draw(hole, board):
    """检测是否有同花听牌（4张同花）"""
    suits = [c.suit for c in hole + board]
    return max(Counter(suits).values()) == 4


def _has_straight_draw(hole, board):
    """检测是否有顺子听牌（双面或内填）"""
    vals = sorted(set(c.val for c in hole + board))
    for i in range(len(vals) - 3):
        window = vals[i:i+4]
        if window[-1] - window[0] <= 4 and len(window) == 4:
            return True
    return False
