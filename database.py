"""
database.py
-----------
数据库层：本地用 SQLite，生产用 PostgreSQL（AWS RDS）
通过 DATABASE_URL 环境变量自动切换
"""

import os
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/trainer.db')
IS_POSTGRES  = DATABASE_URL.startswith('postgresql')


# ── 连接管理 ──────────────────────────────────────────────

@contextmanager
def get_conn():
    """统一的数据库连接上下文管理器"""
    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        import sqlite3
        db_path = DATABASE_URL.replace('sqlite:///', '')
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _ph():
    """占位符：SQLite 用 ?，PostgreSQL 用 %s"""
    return '%s' if IS_POSTGRES else '?'


def _cursor(conn):
    """获取 cursor，PostgreSQL 用 DictCursor"""
    if IS_POSTGRES:
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()


# ── 建表 ──────────────────────────────────────────────────

def init_db():
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)

        # users 表
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id            {'SERIAL' if IS_POSTGRES else 'INTEGER'} PRIMARY KEY {'AUTOINCREMENT' if not IS_POSTGRES else ''},
                username      TEXT NOT NULL UNIQUE,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                last_login    TEXT
            )
        '''.replace('INTEGER PRIMARY KEY AUTOINCREMENT',
                    'INTEGER PRIMARY KEY AUTOINCREMENT' if not IS_POSTGRES else 'SERIAL PRIMARY KEY'))

        # sessions 表
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS sessions (
                id           {'SERIAL' if IS_POSTGRES else 'INTEGER'} PRIMARY KEY {'AUTOINCREMENT' if not IS_POSTGRES else ''},
                user_id      INTEGER REFERENCES users(id),
                started_at   TEXT NOT NULL,
                ended_at     TEXT,
                total_hands  INTEGER DEFAULT 0,
                correct      INTEGER DEFAULT 0
            )
        '''.replace('INTEGER PRIMARY KEY AUTOINCREMENT',
                    'INTEGER PRIMARY KEY AUTOINCREMENT' if not IS_POSTGRES else 'SERIAL PRIMARY KEY'))

        # decisions 表
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS decisions (
                id           {'SERIAL' if IS_POSTGRES else 'INTEGER'} PRIMARY KEY {'AUTOINCREMENT' if not IS_POSTGRES else ''},
                session_id   INTEGER,
                user_id      INTEGER REFERENCES users(id),
                created_at   TEXT NOT NULL,
                street       TEXT NOT NULL,
                position     TEXT NOT NULL,
                hand_str     TEXT NOT NULL,
                hole_cards   TEXT NOT NULL,
                board        TEXT NOT NULL,
                pot          REAL NOT NULL,
                stack        REAL NOT NULL,
                user_action  TEXT NOT NULL,
                gto_action   TEXT NOT NULL,
                is_correct   INTEGER NOT NULL,
                gto_reason   TEXT,
                equity_hero  REAL,
                archetype    TEXT
            )
        '''.replace('INTEGER PRIMARY KEY AUTOINCREMENT',
                    'INTEGER PRIMARY KEY AUTOINCREMENT' if not IS_POSTGRES else 'SERIAL PRIMARY KEY'))

        # 索引（PostgreSQL 和 SQLite 语法一样）
        c.execute('CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')

    print(f'[DB] 初始化完成 ({"PostgreSQL" if IS_POSTGRES else "SQLite"}): {DATABASE_URL[:40]}...')


# ── 用户操作 ──────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str) -> int:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        if IS_POSTGRES:
            c.execute(
                f'INSERT INTO users (username, email, password_hash, created_at) VALUES ({ph},{ph},{ph},{ph}) RETURNING id',
                (username, email, password_hash, datetime.now().isoformat())
            )
            return c.fetchone()['id']
        else:
            c.execute(
                f'INSERT INTO users (username, email, password_hash, created_at) VALUES ({ph},{ph},{ph},{ph})',
                (username, email, password_hash, datetime.now().isoformat())
            )
            return c.lastrowid


def get_user_by_email(email: str) -> dict | None:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'SELECT * FROM users WHERE email={ph}', (email,))
        row = c.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'SELECT id, username, email, created_at, last_login FROM users WHERE id={ph}', (user_id,))
        row = c.fetchone()
        return dict(row) if row else None


def update_last_login(user_id: int):
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'UPDATE users SET last_login={ph} WHERE id={ph}',
                  (datetime.now().isoformat(), user_id))


def email_exists(email: str) -> bool:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'SELECT 1 FROM users WHERE email={ph}', (email,))
        return c.fetchone() is not None


def username_exists(username: str) -> bool:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'SELECT 1 FROM users WHERE username={ph}', (username,))
        return c.fetchone() is not None


# ── Session 操作 ──────────────────────────────────────────

def start_session(user_id: int = None) -> int:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        if IS_POSTGRES:
            c.execute(
                f'INSERT INTO sessions (user_id, started_at) VALUES ({ph},{ph}) RETURNING id',
                (user_id, datetime.now().isoformat())
            )
            return c.fetchone()['id']
        else:
            c.execute(
                f'INSERT INTO sessions (user_id, started_at) VALUES ({ph},{ph})',
                (user_id, datetime.now().isoformat())
            )
            return c.lastrowid


def end_session(session_id: int):
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'''
            UPDATE sessions
            SET ended_at={ph},
                total_hands=(SELECT COUNT(*) FROM decisions WHERE session_id={ph}),
                correct=(SELECT COUNT(*) FROM decisions WHERE session_id={ph} AND is_correct=1)
            WHERE id={ph}
        ''', (datetime.now().isoformat(), session_id, session_id, session_id))


# ── Decision 操作 ─────────────────────────────────────────

def save_decision(session_id: int, scenario: dict,
                  user_action: str, is_correct: bool,
                  user_id: int = None, archetype: str = None):
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'''
            INSERT INTO decisions
                (session_id, user_id, created_at, street, position, hand_str,
                 hole_cards, board, pot, stack,
                 user_action, gto_action, is_correct, gto_reason, archetype)
            VALUES ({','.join([ph]*15)})
        ''', (
            session_id,
            user_id,
            datetime.now().isoformat(),
            scenario.get('street', ''),
            scenario.get('hero_pos', ''),
            scenario.get('hand_str', ''),
            json.dumps(scenario.get('hole_cards', [])),
            json.dumps(scenario.get('board', [])),
            scenario.get('pot', 0),
            scenario.get('stack', 0),
            user_action,
            scenario.get('gto_action', ''),
            int(is_correct),
            scenario.get('gto_reason', ''),
            archetype,
        ))


# ── 统计查询 ──────────────────────────────────────────────

def get_overall_stats(user_id: int = None) -> dict:
    ph = _ph()
    user_filter = f'WHERE user_id={ph}' if user_id else ''
    params      = (user_id,) if user_id else ()

    with get_conn() as conn:
        c = _cursor(conn)

        # 总体
        c.execute(f'SELECT COUNT(*) as total, SUM(is_correct) as correct FROM decisions {user_filter}', params)
        row     = c.fetchone()
        total   = int(row['total']   or 0)
        correct = int(row['correct'] or 0)

        # 按街道
        c.execute(f'''
            SELECT street, COUNT(*) as total, SUM(is_correct) as correct
            FROM decisions {user_filter}
            GROUP BY street
        ''', params)
        by_street = {}
        for r in c.fetchall():
            pct = round(int(r['correct']) / int(r['total']) * 100, 1) if r['total'] else 0
            by_street[r['street']] = {'total': int(r['total']), 'correct': int(r['correct']), 'pct': pct}

        # 按位置
        c.execute(f'''
            SELECT position, COUNT(*) as total, SUM(is_correct) as correct
            FROM decisions {user_filter}
            GROUP BY position
        ''', params)
        by_position = {}
        for r in c.fetchall():
            pct = round(int(r['correct']) / int(r['total']) * 100, 1) if r['total'] else 0
            by_position[r['position']] = {'total': int(r['total']), 'correct': int(r['correct']), 'pct': pct}

        # 按对手形象
        c.execute(f'''
            SELECT archetype, COUNT(*) as total, SUM(is_correct) as correct
            FROM decisions {user_filter} {'AND' if user_filter else 'WHERE'} archetype IS NOT NULL
            GROUP BY archetype
        ''', params)
        by_archetype = {}
        for r in c.fetchall():
            pct = round(int(r['correct']) / int(r['total']) * 100, 1) if r['total'] else 0
            by_archetype[r['archetype']] = {'total': int(r['total']), 'correct': int(r['correct']), 'pct': pct}

        # 薄弱手牌
        c.execute(f'''
            SELECT hand_str, COUNT(*) as total, SUM(is_correct) as correct
            FROM decisions {user_filter}
            GROUP BY hand_str
            HAVING COUNT(*) >= 3
            ORDER BY (CAST(SUM(is_correct) AS FLOAT)/COUNT(*)) ASC
            LIMIT 10
        ''', params)
        weak_hands = []
        for r in c.fetchall():
            pct = round(int(r['correct']) / int(r['total']) * 100, 1)
            weak_hands.append({'hand': r['hand_str'], 'total': int(r['total']),
                                'correct': int(r['correct']), 'pct': pct})

        # 最近记录
        c.execute(f'''
            SELECT street, position, hand_str, user_action, gto_action,
                   is_correct, created_at, archetype
            FROM decisions {user_filter}
            ORDER BY created_at DESC LIMIT 20
        ''', params)
        recent = [dict(r) for r in c.fetchall()]

        # 场次历史
        sess_filter = f'WHERE user_id={ph}' if user_id else ''
        c.execute(f'''
            SELECT id, started_at, ended_at, total_hands, correct
            FROM sessions {sess_filter}
            ORDER BY started_at DESC LIMIT 10
        ''', params)
        sessions = [dict(r) for r in c.fetchall()]

    pct = round(correct / total * 100, 1) if total else 0
    return {
        'total':        total,
        'correct':      correct,
        'pct':          pct,
        'by_street':    by_street,
        'by_position':  by_position,
        'by_archetype': by_archetype,
        'weak_hands':   weak_hands,
        'recent':       recent,
        'sessions':     sessions,
    }


def get_session_stats(session_id: int) -> dict:
    ph = _ph()
    with get_conn() as conn:
        c = _cursor(conn)
        c.execute(f'''
            SELECT street, position, hand_str, user_action, gto_action, is_correct, gto_reason
            FROM decisions WHERE session_id={ph} ORDER BY created_at
        ''', (session_id,))
        rows    = [dict(r) for r in c.fetchall()]
        total   = len(rows)
        correct = sum(1 for r in rows if r['is_correct'])
        return {
            'decisions': rows,
            'total':     total,
            'correct':   correct,
            'pct':       round(correct / total * 100, 1) if total else 0,
        }
