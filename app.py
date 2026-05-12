"""
app.py
------
Flask 后端：整合账号系统、多街手牌、Redis存储、双数据库支持
"""

import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, render_template, g
from poker_engine import calc_equity, pot_odds, calc_ev, random_scenario
from hand_engine import start_new_hand, apply_hero_action, finalize_hand
from database import (
    init_db, start_session, end_session, save_decision,
    get_overall_stats, get_session_stats,
    create_user, get_user_by_email, get_user_by_id,
    update_last_login, email_exists, username_exists,
)
from opponents import generate_opponent, get_all_archetypes_summary
from auth import (
    generate_token, hash_password, check_password,
    require_auth, optional_auth, validate_register, validate_login,
)
from store import save_hand, load_hand, delete_hand, is_redis_connected

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

init_db()


# ═══════════════════════════════════════════════════════════
#  页面路由
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stats')
def stats_page():
    return render_template('stats.html')

@app.route('/info')
def info_page():
    return render_template('info.html')


# ═══════════════════════════════════════════════════════════
#  API：账号系统
# ═══════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data   = request.get_json() or {}
    errors = validate_register(data)
    if errors:
        return jsonify({'error': errors[0]}), 400

    username = data['username'].strip()
    email    = data['email'].strip().lower()
    password = data['password']

    if email_exists(email):
        return jsonify({'error': 'Email already registered'}), 409
    if username_exists(username):
        return jsonify({'error': 'Username already taken'}), 409

    user_id = create_user(username, email, hash_password(password))
    token   = generate_token(user_id, username)

    return jsonify({
        'token':    token,
        'user_id':  user_id,
        'username': username,
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data   = request.get_json() or {}
    errors = validate_login(data)
    if errors:
        return jsonify({'error': errors[0]}), 400

    email = data['email'].strip().lower()
    user  = get_user_by_email(email)

    if not user or not check_password(data['password'], user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    update_last_login(user['id'])
    token = generate_token(user['id'], user['username'])

    return jsonify({
        'token':    token,
        'user_id':  user['id'],
        'username': user['username'],
    })


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def api_me():
    user = get_user_by_id(g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user)


# ═══════════════════════════════════════════════════════════
#  API：训练 Session
# ═══════════════════════════════════════════════════════════

@app.route('/api/session/start', methods=['POST'])
@optional_auth
def api_start_session():
    sid = start_session(user_id=g.user_id)
    return jsonify({'session_id': sid, 'status': 'started'})


@app.route('/api/session/end', methods=['POST'])
@optional_auth
def api_end_session():
    data = request.get_json() or {}
    sid  = data.get('session_id')
    if not sid:
        return jsonify({'error': 'session_id required'}), 400
    end_session(sid)
    stats = get_session_stats(sid)
    return jsonify({'status': 'ended', 'summary': stats})


# ═══════════════════════════════════════════════════════════
#  API：多街连贯手牌
# ═══════════════════════════════════════════════════════════

@app.route('/api/hand/start', methods=['POST'])
@optional_auth
def api_hand_start():
    """
    开始一手新牌
    Body: { archetype: 'fish', session_id: 1 }
    """
    data      = request.get_json() or {}
    archetype = data.get('archetype')   # 可选，不传则随机

    hand = start_new_hand(archetype)
    save_hand(hand.hand_id, hand)

    return jsonify(hand.to_dict())


@app.route('/api/hand/action', methods=['POST'])
@optional_auth
def api_hand_action():
    """
    提交行动，推进到下一街
    Body: { hand_id: 'abc123', action: 'raise' }
    """
    data    = request.get_json() or {}
    hand_id = data.get('hand_id')
    action  = data.get('action')

    if not hand_id or not action:
        return jsonify({'error': 'hand_id and action required'}), 400

    hand = load_hand(hand_id)
    if not hand:
        return jsonify({'error': 'Hand not found or expired'}), 404

    # 如果已经在河牌，直接进入总结
    if hand.current_street == 'river' and len(hand.streets) >= 4:
        hand = apply_hero_action(hand, action)
        summary = finalize_hand(hand)
        _save_hand_to_db(hand, summary, data.get('session_id'), g.user_id)
        delete_hand(hand_id)
        return jsonify({'done': True, 'summary': summary})

    hand = apply_hero_action(hand, action)

    # 手牌提前结束（弃牌或对手弃牌）
    if hand.is_complete:
        summary = finalize_hand(hand)
        _save_hand_to_db(hand, summary, data.get('session_id'), g.user_id)
        delete_hand(hand_id)
        return jsonify({'done': True, 'summary': summary})

    save_hand(hand_id, hand)
    return jsonify({'done': False, 'hand': hand.to_dict()})


@app.route('/api/hand/abandon', methods=['POST'])
def api_hand_abandon():
    """放弃当前手牌（不保存记录）"""
    data    = request.get_json() or {}
    hand_id = data.get('hand_id')
    if hand_id:
        delete_hand(hand_id)
    return jsonify({'status': 'abandoned'})


# ═══════════════════════════════════════════════════════════
#  API：计算工具
# ═══════════════════════════════════════════════════════════

@app.route('/api/calc/pot_odds', methods=['POST'])
def api_pot_odds():
    data = request.get_json() or {}
    try:
        result = pot_odds(float(data['pot']), float(data['bet']))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/calc/equity', methods=['POST'])
def api_calc_equity():
    from poker_engine import Card
    data = request.get_json() or {}
    try:
        def parse_card(s):
            return Card(s[0].upper(), s[1].lower())
        hero    = [parse_card(c) for c in data['hero']]
        villain = [parse_card(c) for c in data['villain']] if data.get('villain') else None
        board   = [parse_card(c) for c in data.get('board', [])]
        sims    = int(data.get('sims', 800))
        result  = calc_equity(hero, villain, board, simulations=sims)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/calc/ev', methods=['POST'])
def api_calc_ev():
    data = request.get_json() or {}
    try:
        result = calc_ev(
            float(data['pot']), float(data['bet']),
            float(data['fold_pct']), float(data['equity_pct'])
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ═══════════════════════════════════════════════════════════
#  API：对手形象
# ═══════════════════════════════════════════════════════════

@app.route('/api/opponent/random', methods=['GET'])
def api_random_opponent():
    archetype = request.args.get('archetype')
    return jsonify(generate_opponent(archetype))


@app.route('/api/opponent/archetypes', methods=['GET'])
def api_archetypes():
    return jsonify(get_all_archetypes_summary())


# ═══════════════════════════════════════════════════════════
#  API：统计
# ═══════════════════════════════════════════════════════════

@app.route('/api/stats', methods=['GET'])
@optional_auth
def api_stats():
    # 登录用户看自己的数据，未登录看全局
    stats = get_overall_stats(user_id=g.user_id)
    return jsonify(stats)


@app.route('/api/stats/session/<int:session_id>', methods=['GET'])
def api_session_stats(session_id):
    return jsonify(get_session_stats(session_id))


# ═══════════════════════════════════════════════════════════
#  API：系统状态
# ═══════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'ok',
        'redis':  is_redis_connected(),
        'db':     'postgresql' if os.getenv('DATABASE_URL', '').startswith('postgresql') else 'sqlite',
    })


# ═══════════════════════════════════════════════════════════
#  内部工具函数
# ═══════════════════════════════════════════════════════════

def _save_hand_to_db(hand, summary, session_id, user_id):
    """把手牌每条街的决策存入数据库"""
    if not session_id:
        return
    for review in summary.get('street_reviews', []):
        if review.get('hero_action') is None:
            continue
        scenario = {
            'street':     review['street'],
            'hero_pos':   hand.hero_pos,
            'hand_str':   summary['hand_str'],
            'hole_cards': [c.to_dict() for c in hand.hero_hole],
            'board':      [c.to_dict() for c in hand.board],
            'pot':        hand.pot,
            'stack':      hand.stack,
            'gto_action': review.get('gto_action') or 'check',
            'gto_reason': review.get('reason_zh') or '',
        }
        save_decision(
            session_id  = session_id,
            scenario    = scenario,
            user_action = review.get('hero_action') or 'check',
            is_correct  = bool(review.get('is_correct')),
            user_id     = user_id,
            archetype   = hand.archetype,
        )


# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('GTO Trainer v2 启动中...')
    print(f'DB: {"PostgreSQL" if os.getenv("DATABASE_URL","").startswith("postgresql") else "SQLite"}')
    print(f'Redis: {"已配置" if os.getenv("REDIS_URL") else "未配置（降级到内存）"}')
    app.run(debug=True, port=5002)
