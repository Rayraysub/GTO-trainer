"""
auth.py
-------
账号系统：注册、登录、JWT验证中间件
"""

import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g

JWT_SECRET  = os.getenv('JWT_SECRET', 'dev-jwt-secret')
JWT_EXPIRY  = int(os.getenv('JWT_EXPIRY_HOURS', 168))  # 默认7天


# ── Token 工具 ────────────────────────────────────────────

def generate_token(user_id: int, username: str) -> str:
    payload = {
        'user_id':  user_id,
        'username': username,
        'exp':      datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY),
        'iat':      datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── 密码工具 ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── 中间件装饰器 ──────────────────────────────────────────

def require_auth(f):
    """
    JWT 验证中间件，用法：
    @app.route('/api/xxx')
    @require_auth
    def my_route():
        user_id = g.user_id   # 从 token 中提取
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid token'}), 401

        token   = auth_header.split(' ', 1)[1]
        payload = verify_token(token)
        if not payload:
            return jsonify({'error': 'Token expired or invalid'}), 401

        g.user_id  = payload['user_id']
        g.username = payload['username']
        return f(*args, **kwargs)
    return decorated


def optional_auth(f):
    """
    可选验证，有 token 就设置 user_id，没有也不报错
    用于兼容未登录用户
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        g.user_id  = None
        g.username = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token   = auth_header.split(' ', 1)[1]
            payload = verify_token(token)
            if payload:
                g.user_id  = payload['user_id']
                g.username = payload['username']
        return f(*args, **kwargs)
    return decorated


# ── 输入验证 ──────────────────────────────────────────────

def validate_register(data: dict) -> list[str]:
    errors = []
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or len(username) < 2:
        errors.append('Username must be at least 2 characters')
    if len(username) > 30:
        errors.append('Username too long (max 30 chars)')
    if not email or '@' not in email:
        errors.append('Valid email required')
    if not password or len(password) < 6:
        errors.append('Password must be at least 6 characters')
    return errors


def validate_login(data: dict) -> list[str]:
    errors = []
    if not data.get('email'):
        errors.append('Email required')
    if not data.get('password'):
        errors.append('Password required')
    return errors
