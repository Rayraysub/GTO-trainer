"""
opponents.py
------------
对手形象系统：统计数据、牌手类型、剥削性策略建议
"""

import random

# ── 牌手类型定义 ──────────────────────────────────────────
ARCHETYPES = {
    'fish': {
        'name': '鱼型（Fish）',
        'emoji': '🐟',
        'description': '入池太多、弃牌太多、很少加注。最容易被剥削的对手。',
        'color': '#E6F1FB',
        'text_color': '#0C447C',
        'stats': {
            'vpip':         (45, 70),   # 入池率
            'pfr':          (5,  15),   # 翻前加注率
            'three_bet':    (2,   5),   # 3bet率
            'fold_to_3bet': (60, 80),   # 面对3bet弃牌率
            'cbet':         (30, 55),   # c-bet频率
            'fold_to_cbet': (55, 75),   # 面对cbet弃牌率
            'wtsd':         (25, 35),   # 走到摊牌率
            'aggression':   (0.5, 1.2), # 攻击性系数
        },
        'exploits': {
            'preflop': [
                '扩大开牌范围，对手会用太多弱牌入池',
                '减少3bet bluff，对手跟注太多；增加3bet value范围',
                '面对对手加注可以更宽松跟注，对手范围弱',
            ],
            'flop': [
                'Fold to Cbet高：大量c-bet，包括弱牌和bluff',
                '对手check跟注后通常有弱牌，继续施压',
                '避免慢玩，直接大注建底池',
            ],
            'turn': [
                '继续大注，对手很少在转牌弃牌强牌',
                '对手的跟注范围通常是弱对子或听牌',
                '有强牌时不要慢玩，对手不会弃牌',
            ],
            'river': [
                '对手Wtsd低：对手不常走到摊牌，大注bluff有效',
                '有价值牌时选择大注，对手跟注范围弱',
                '避免薄价值注，对手可能突然有强牌',
            ],
        }
    },
    'calling_station': {
        'name': '站型（Calling Station）',
        'emoji': '📞',
        'description': '入池很多、几乎不弃牌、很少加注。价值牌必赚，bluff必亏。',
        'color': '#FAECE7',
        'text_color': '#712B13',
        'stats': {
            'vpip':         (50, 75),
            'pfr':          (5,  12),
            'three_bet':    (1,   4),
            'fold_to_3bet': (20, 45),
            'cbet':         (25, 45),
            'fold_to_cbet': (15, 35),
            'wtsd':         (40, 55),
            'aggression':   (0.3, 0.8),
        },
        'exploits': {
            'preflop': [
                '面对这类对手永远不要bluff 3bet，只用强牌3bet',
                '可以宽松入池，隐含赔率极高',
                '他们的加注几乎都是强牌，要小心',
            ],
            'flop': [
                'Fold to Cbet极低：停止bluff，只有强牌才c-bet',
                '有强牌时大注，对手会用任何对子跟注',
                'Check强牌引诱对手下注（慢玩有效）',
            ],
            'turn': [
                '继续大注获取价值，对手不会弃牌中等强牌',
                '完全停止bluff，对手几乎不弃牌',
                '用坚果或强牌全押，对手经常跟注',
            ],
            'river': [
                '河牌大注甚至全押，对手会用两对以下跟注',
                '绝对不要bluff，这是最大的错误',
                'Wtsd高：对手喜欢看牌，给他们机会付钱',
            ],
        }
    },
    'tag': {
        'name': 'TAG（紧凶型）',
        'emoji': '🎯',
        'description': '入池率低、加注率高、位置意识强。标准GTO打法，最难对付。',
        'color': '#EAF3DE',
        'text_color': '#27500A',
        'stats': {
            'vpip':         (18, 28),
            'pfr':          (14, 22),
            'three_bet':    (6,  10),
            'fold_to_3bet': (45, 60),
            'cbet':         (55, 75),
            'fold_to_cbet': (40, 55),
            'wtsd':         (22, 30),
            'aggression':   (2.0, 3.5),
        },
        'exploits': {
            'preflop': [
                'VPIP/PFR接近：范围强，不要轻易3bet bluff',
                '面对他们的加注需要更强的手牌跟注',
                '可以对他们进行steal，他们会放弃盲注',
        ],
            'flop': [
                'C-bet频率高但有范围：可以float（跟注等转牌）',
                '面对他们的大注要小心，通常有强牌',
                '在有利位置可以加注bluff，对手会考虑弃牌',
            ],
            'turn': [
                '对手在转牌继续下注通常有强牌，需要强牌才跟注',
                '如果对手check转牌，他们的范围变弱，可以施压',
                '位置优势很重要，尽量IP对抗TAG',
            ],
            'river': [
                '对手河牌下注范围通常是极化的（坚果或bluff）',
                '需要用频率理论决定是否跟注，不能只看牌面',
                '他们的bluff频率接近GTO，不要过度弃牌',
            ],
        }
    },
    'lag': {
        'name': 'LAG（松凶型）',
        'emoji': '🔥',
        'description': '入池率高、加注频繁、攻击性强。范围宽，但经验丰富时难以对付。',
        'color': '#FAEEDA',
        'text_color': '#633806',
        'stats': {
            'vpip':         (30, 45),
            'pfr':          (22, 35),
            'three_bet':    (10, 18),
            'fold_to_3bet': (35, 55),
            'cbet':         (65, 85),
            'fold_to_cbet': (35, 50),
            'wtsd':         (25, 35),
            'aggression':   (3.0, 5.0),
        },
        'exploits': {
            'preflop': [
                '3bet范围要扩大，对手VPIP高说明范围弱',
                '面对他们的开牌可以更宽松跟注（隐含赔率好）',
                '4bet bluff有效，他们的3bet范围宽但弱',
            ],
            'flop': [
                'C-bet频率很高但范围弱：可以加注bluff',
                'Check-raise有效，对手c-bet太多弱牌',
                '用强牌慢玩引诱，对手会继续施压',
            ],
            'turn': [
                '面对对手转牌继续下注，可以更宽松跟注',
                '他们的double barrel通常包含很多bluff',
                '有强牌时可以check-raise，对手会下注',
            ],
            'river': [
                '对手river下注范围包含大量bluff，可以宽松跟注',
                '用中等强牌（两对）跟注有利可图',
                '不要在对手激进时过度弃牌',
            ],
        }
    },
    'nit': {
        'name': 'Nit（超紧型）',
        'emoji': '🪨',
        'description': '入池率极低、只玩顶级手牌。遇到他们的加注直接弃牌。',
        'color': '#EEEDFE',
        'text_color': '#3C3489',
        'stats': {
            'vpip':         (8,  16),
            'pfr':          (7,  13),
            'three_bet':    (2,   5),
            'fold_to_3bet': (65, 80),
            'cbet':         (50, 65),
            'fold_to_cbet': (50, 65),
            'wtsd':         (18, 25),
            'aggression':   (1.5, 2.5),
        },
        'exploits': {
            'preflop': [
                'VPIP极低：大量steal他们的盲注，他们经常弃牌',
                '面对他们的加注需要顶级手牌，范围极强',
                '3bet他们很有效，他们fold to 3bet很高',
            ],
            'flop': [
                '大量c-bet，对手翻前跟注范围强但窄',
                '面对对手加注立即弃牌，他们只加注强牌',
                '可以频繁bluff，对手fold to cbet高',
            ],
            'turn': [
                '对手check通常意味着弱牌，继续施压',
                '面对对手转牌加注：弃牌，他们不会用弱牌加注',
                'Barrel频率可以高，对手不喜欢在没有强牌时跟注',
            ],
            'river': [
                '大量bluff，对手不喜欢用中等牌走到河牌',
                '面对对手river下注：几乎只有坚果才跟注',
                '价值注要小心，对手可能早就弃牌了',
            ],
        }
    }
}


def generate_opponent(archetype: str = None) -> dict:
    """
    生成一个随机对手，可以指定类型或随机生成
    """
    if archetype is None:
        # 加权随机，实战中各类型出现频率
        weights = {'fish': 30, 'calling_station': 20, 'tag': 25, 'lag': 15, 'nit': 10}
        archetype = random.choices(list(weights.keys()), weights=list(weights.values()))[0]

    profile = ARCHETYPES[archetype]
    stats_ranges = profile['stats']

    # 在范围内随机生成具体数值
    stats = {}
    for stat, (lo, hi) in stats_ranges.items():
        if isinstance(lo, float) or isinstance(hi, float):
            stats[stat] = round(random.uniform(lo, hi), 1)
        else:
            stats[stat] = random.randint(lo, hi)

    return {
        'archetype':   archetype,
        'name':        profile['name'],
        'emoji':       profile['emoji'],
        'description': profile['description'],
        'color':       profile['color'],
        'text_color':  profile['text_color'],
        'stats':       stats,
        'exploits':    profile['exploits'],
    }


def get_exploit_advice(opponent: dict, street: str, action_context: str = None) -> dict:
    """
    根据对手形象和当前街道给出剥削性建议
    返回：建议列表 + 关键统计数据
    """
    exploits = opponent['exploits'].get(street, [])
    stats = opponent['stats']
    archetype = opponent['archetype']

    # 计算关键指标的偏差（相对于GTO均衡）
    insights = []

    fold_to_cbet = stats['fold_to_cbet']
    if fold_to_cbet > 55:
        insights.append({
            'stat': f"Fold to Cbet: {fold_to_cbet}%",
            'signal': '↑ 弃牌太多',
            'action': '增加bluff频率',
            'color': '#1D9E75'
        })
    elif fold_to_cbet < 35:
        insights.append({
            'stat': f"Fold to Cbet: {fold_to_cbet}%",
            'signal': '↓ 跟注太多',
            'action': '停止bluff，只下注强牌',
            'color': '#E24B4A'
        })

    fold_to_3bet = stats['fold_to_3bet']
    if fold_to_3bet > 65:
        insights.append({
            'stat': f"Fold to 3bet: {fold_to_3bet}%",
            'signal': '↑ 面对3bet太弱',
            'action': '扩大3bet bluff范围',
            'color': '#1D9E75'
        })
    elif fold_to_3bet < 40:
        insights.append({
            'stat': f"Fold to 3bet: {fold_to_3bet}%",
            'signal': '↓ 面对3bet不弃牌',
            'action': '只用价值牌3bet',
            'color': '#E24B4A'
        })

    wtsd = stats['wtsd']
    if wtsd > 38:
        insights.append({
            'stat': f"WTSD: {wtsd}%",
            'signal': '↑ 喜欢走到摊牌',
            'action': '薄价值注有效，停止bluff',
            'color': '#E24B4A'
        })
    elif wtsd < 22:
        insights.append({
            'stat': f"WTSD: {wtsd}%",
            'signal': '↓ 不喜欢走到摊牌',
            'action': 'River bluff有效',
            'color': '#1D9E75'
        })

    return {
        'exploits': exploits,
        'insights': insights,
    }


def evaluate_exploitative_decision(opponent: dict, street: str,
                                    user_action: str, gto_action: str,
                                    pot: float, bet_size: float = None) -> dict:
    """
    评估玩家的决策是否根据对手形象做出了正确调整
    返回：是否正确调整 + 详细解释
    """
    stats = opponent['stats']
    archetype = opponent['archetype']
    fold_to_cbet = stats['fold_to_cbet']
    wtsd = stats['wtsd']

    # 计算GTO最优弃牌率（如果有下注额）
    gto_fold_rate = None
    if bet_size:
        gto_fold_rate = round(bet_size / (pot + bet_size) * 100, 1)

    # 判断逻辑
    is_exploit_correct = True
    explanation = []
    adjustment = None

    # 场景1：对手fold to cbet很高，应该bluff
    if fold_to_cbet > 55 and street in ['flop', 'turn']:
        if user_action in ['bet', 'raise']:
            explanation.append(f"✓ 对手 Fold to Cbet={fold_to_cbet}%（高于GTO均衡），你选择下注是正确的剥削。")
        elif user_action == 'check':
            is_exploit_correct = False
            explanation.append(f"✗ 对手 Fold to Cbet={fold_to_cbet}%，他弃牌太多，这里应该下注而不是过牌。")
            adjustment = 'should_bet'

    # 场景2：对手fold to cbet很低（Calling Station），不应该bluff
    elif fold_to_cbet < 35 and street in ['flop', 'turn']:
        if user_action == 'check':
            explanation.append(f"✓ 对手 Fold to Cbet={fold_to_cbet}%（很低），过牌控制底池是正确的。")
        elif user_action in ['bet', 'raise'] and gto_action == 'check':
            is_exploit_correct = False
            explanation.append(f"✗ 对手 Fold to Cbet={fold_to_cbet}%（Calling Station），对弱牌下注会亏钱。")
            adjustment = 'should_check'

    # 场景3：Nit类型，可以大量steal
    if archetype == 'nit' and street == 'preflop':
        if user_action == 'raise':
            explanation.append(f"✓ 对手是Nit，VPIP只有{stats['vpip']}%，steal盲注很有效。")

    # 场景4：Calling Station，river不应该bluff
    if archetype == 'calling_station' and street == 'river':
        if user_action in ['bet', 'raise'] and gto_action == 'check':
            is_exploit_correct = False
            explanation.append(f"✗ Calling Station的WTSD={wtsd}%，他们不弃牌，river bluff必亏。")
            adjustment = 'should_check'
        elif user_action in ['bet', 'raise'] and gto_action in ['bet', 'raise']:
            explanation.append(f"✓ 有价值牌对Calling Station下注非常正确，他们会用弱牌跟注。")

    if not explanation:
        explanation.append("这个决策在此对手形象下没有特别的剥削机会，按GTO打即可。")

    return {
        'is_exploit_correct': is_exploit_correct,
        'explanation':        explanation,
        'adjustment':         adjustment,
        'gto_fold_rate':      gto_fold_rate,
        'key_stat':           f"Fold to Cbet: {fold_to_cbet}% | WTSD: {wtsd}% | Aggression: {stats['aggression']}",
    }


def get_all_archetypes_summary() -> list:
    """返回所有牌手类型的简介，用于前端展示"""
    return [
        {
            'id':          k,
            'name':        v['name'],
            'emoji':       v['emoji'],
            'description': v['description'],
            'color':       v['color'],
            'text_color':  v['text_color'],
            'vpip_range':  f"{v['stats']['vpip'][0]}-{v['stats']['vpip'][1]}%",
            'pfr_range':   f"{v['stats']['pfr'][0]}-{v['stats']['pfr'][1]}%",
        }
        for k, v in ARCHETYPES.items()
    ]
