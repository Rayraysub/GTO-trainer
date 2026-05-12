"""
villain_simulator.py
--------------------
对手行动模拟器：根据牌手形象和当前局面模拟对手的真实行动
每种形象有不同的行动概率分布，让多街训练有意义
"""

import random
from poker_engine import best_hand_from_7, Card, RANK_VAL

# ── 各形象的行动概率配置 ──────────────────────────────────
ARCHETYPE_CONFIG = {
    'fish': {
        'preflop_open_range': 0.55,      # 55% 手牌会入池
        'preflop_3bet_pct':   0.04,      # 面对开牌3bet概率
        'fold_to_3bet':       0.50,      # 面对3bet弃牌率
        'flop_cbet_call':     0.65,      # 面对cbet跟注率
        'flop_cbet_raise':    0.05,      # 面对cbet加注率
        'flop_donk_bet':      0.15,      # 主动donk bet概率
        'turn_barrel_call':   0.55,      # 面对转牌下注跟注率
        'turn_barrel_raise':  0.04,
        'river_call':         0.50,      # 面对河牌下注跟注率
        'river_bluff':        0.05,      # 河牌bluff概率
        'wtsd':               0.30,
    },
    'calling_station': {
        'preflop_open_range': 0.65,
        'preflop_3bet_pct':   0.02,
        'fold_to_3bet':       0.25,
        'flop_cbet_call':     0.80,
        'flop_cbet_raise':    0.03,
        'flop_donk_bet':      0.10,
        'turn_barrel_call':   0.75,
        'turn_barrel_raise':  0.03,
        'river_call':         0.72,
        'river_bluff':        0.02,
        'wtsd':               0.48,
    },
    'tag': {
        'preflop_open_range': 0.22,
        'preflop_3bet_pct':   0.09,
        'fold_to_3bet':       0.52,
        'flop_cbet_call':     0.45,
        'flop_cbet_raise':    0.12,
        'flop_donk_bet':      0.08,
        'turn_barrel_call':   0.40,
        'turn_barrel_raise':  0.10,
        'river_call':         0.35,
        'river_bluff':        0.20,
        'wtsd':               0.26,
    },
    'lag': {
        'preflop_open_range': 0.38,
        'preflop_3bet_pct':   0.15,
        'fold_to_3bet':       0.42,
        'flop_cbet_call':     0.48,
        'flop_cbet_raise':    0.20,
        'flop_donk_bet':      0.22,
        'turn_barrel_call':   0.45,
        'turn_barrel_raise':  0.18,
        'river_call':         0.40,
        'river_bluff':        0.30,
        'wtsd':               0.30,
    },
    'nit': {
        'preflop_open_range': 0.12,
        'preflop_3bet_pct':   0.03,
        'fold_to_3bet':       0.72,
        'flop_cbet_call':     0.38,
        'flop_cbet_raise':    0.08,
        'flop_donk_bet':      0.05,
        'turn_barrel_call':   0.32,
        'turn_barrel_raise':  0.07,
        'river_call':         0.28,
        'river_bluff':        0.08,
        'wtsd':               0.22,
    },
}

# 行动文字
ACTION_LABELS = {
    'fold':  {'zh': '弃牌',     'en': 'Fold'},
    'call':  {'zh': '跟注',     'en': 'Call'},
    'check': {'zh': '过牌',     'en': 'Check'},
    'raise': {'zh': '加注',     'en': 'Raise'},
    'bet':   {'zh': '下注',     'en': 'Bet'},
    'allin': {'zh': '全押',     'en': 'All-in'},
    '3bet':  {'zh': '3-Bet',    'en': '3-Bet'},
}


class VillainSimulator:
    def __init__(self, archetype: str):
        self.archetype = archetype
        self.cfg = ARCHETYPE_CONFIG.get(archetype, ARCHETYPE_CONFIG['tag'])
        # 对手的隐藏手牌强度（0-1），在每手牌开始时随机设定
        self._hand_strength = random.random()
        # 对手是否持有强牌（影响多街行动一致性）
        self._has_strong_hand = self._hand_strength > 0.7
        self._has_medium_hand = 0.35 < self._hand_strength <= 0.7
        self._has_draw = random.random() < 0.25

    def preflop_action(self, hero_raised: bool = False) -> dict:
        """
        翻前对手行动
        hero_raised: 你是否已经开牌加注
        返回对手的行动和描述
        """
        cfg = self.cfg

        if not hero_raised:
            # 对手先行动（你在大盲注）
            if random.random() < cfg['preflop_open_range']:
                return self._action('raise', '对手开牌加注', 'Villain raises')
            else:
                return self._action('fold', '对手弃牌', 'Villain folds')
        else:
            # 面对你的开牌加注
            if random.random() < cfg['preflop_3bet_pct']:
                return self._action('3bet', '对手3bet', 'Villain 3-bets')
            elif random.random() < (1 - cfg['fold_to_3bet']):
                return self._action('call', '对手跟注', 'Villain calls')
            else:
                return self._action('fold', '对手弃牌', 'Villain folds')

    def flop_action(self, hero_bet: bool = False, pot: float = 10.0) -> dict:
        """翻牌对手行动"""
        cfg = self.cfg

        if hero_bet:
            # 面对你的c-bet
            r = random.random()
            if self._has_strong_hand and r < 0.3:
                return self._action('raise', '对手加注（可能有强牌）', 'Villain raises (likely strong hand)')
            elif r < cfg['flop_cbet_call']:
                return self._action('call', '对手跟注', 'Villain calls')
            else:
                return self._action('fold', '对手弃牌', 'Villain folds')
        else:
            # 你过牌，对手行动
            if self._has_strong_hand and random.random() < 0.55:
                return self._action('bet', '对手下注（可能有强牌）', 'Villain bets (likely strong hand)')
            elif random.random() < cfg['flop_donk_bet']:
                return self._action('bet', '对手主动下注', 'Villain bets')
            else:
                return self._action('check', '对手过牌', 'Villain checks')

    def turn_action(self, hero_bet: bool = False) -> dict:
        """转牌对手行动"""
        cfg = self.cfg

        if hero_bet:
            r = random.random()
            if self._has_strong_hand and r < 0.25:
                return self._action('raise', '对手加注（强牌信号）', 'Villain raises (strong signal)')
            elif r < cfg['turn_barrel_call']:
                return self._action('call', '对手跟注', 'Villain calls')
            else:
                return self._action('fold', '对手弃牌', 'Villain folds')
        else:
            if self._has_strong_hand and random.random() < 0.60:
                return self._action('bet', '对手下注（强牌）', 'Villain bets (strong hand)')
            elif self._has_draw and random.random() < 0.30:
                return self._action('bet', '对手下注（可能在听牌）', 'Villain bets (possible draw)')
            else:
                return self._action('check', '对手过牌', 'Villain checks')

    def river_action(self, hero_bet: bool = False) -> dict:
        """河牌对手行动"""
        cfg = self.cfg

        if hero_bet:
            r = random.random()
            if self._has_strong_hand and r < cfg['river_call'] + 0.15:
                return self._action('call', '对手跟注（强牌）', 'Villain calls (strong hand)')
            elif r < cfg['river_call']:
                return self._action('call', '对手跟注', 'Villain calls')
            else:
                return self._action('fold', '对手弃牌', 'Villain folds')
        else:
            if self._has_strong_hand and random.random() < 0.65:
                return self._action('bet', '对手下注（价值）', 'Villain bets (value)')
            elif random.random() < cfg['river_bluff']:
                return self._action('bet', '对手下注（可能bluff）', 'Villain bets (possible bluff)')
            else:
                return self._action('check', '对手过牌', 'Villain checks')

    def _action(self, action: str, desc_zh: str, desc_en: str) -> dict:
        return {
            'action':   action,
            'desc_zh':  desc_zh,
            'desc_en':  desc_en,
            'archetype': self.archetype,
        }

    def get_read(self) -> dict:
        """
        根据对手的行动线路给出读牌提示
        用于在手牌结束后展示给玩家参考
        """
        reads_zh = []
        reads_en = []

        if self._has_strong_hand:
            reads_zh.append('对手的行动线路一致性强，可能持有强牌')
            reads_en.append('Villain\'s line is consistent — likely a strong hand')
        if self._has_draw:
            reads_zh.append('对手可能在听牌（同花或顺子）')
            reads_en.append('Villain may be on a draw (flush or straight)')
        if not self._has_strong_hand and not self._has_draw:
            reads_zh.append('对手的行动偏被动，手牌可能较弱')
            reads_en.append('Villain played passively — likely a weak hand')

        return {'zh': reads_zh, 'en': reads_en}
