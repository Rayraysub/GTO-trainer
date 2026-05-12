"""
store.py
--------
手牌状态存储层：优先用 Redis，本地开发降级到内存 dict
生产环境用 AWS ElastiCache Redis
"""

import os
import json
import pickle
from typing import Optional

REDIS_URL = os.getenv('REDIS_URL', '')

# ── Redis 连接（失败则降级）────────────────────────────────

_redis_client = None
_memory_store: dict = {}   # 降级用的内存存储


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=False)
        client.ping()
        _redis_client = client
        print(f'[Store] Redis 连接成功: {REDIS_URL}')
        return _redis_client
    except Exception as e:
        print(f'[Store] Redis 连接失败，降级到内存存储: {e}')
        return None


# ── 公共接口 ──────────────────────────────────────────────

HAND_TTL = 3600   # 手牌状态保留1小时（防止内存泄漏）


def save_hand(hand_id: str, hand_obj) -> bool:
    """序列化并保存手牌状态"""
    data = pickle.dumps(hand_obj)
    r = _get_redis()
    if r:
        try:
            r.setex(f'hand:{hand_id}', HAND_TTL, data)
            return True
        except Exception as e:
            print(f'[Store] Redis save error: {e}')
    # 降级到内存
    _memory_store[f'hand:{hand_id}'] = data
    return True


def load_hand(hand_id: str) -> Optional[object]:
    """加载并反序列化手牌状态"""
    r = _get_redis()
    if r:
        try:
            data = r.get(f'hand:{hand_id}')
            if data:
                return pickle.loads(data)
        except Exception as e:
            print(f'[Store] Redis load error: {e}')
    # 降级到内存
    data = _memory_store.get(f'hand:{hand_id}')
    return pickle.loads(data) if data else None


def delete_hand(hand_id: str):
    """手牌完成后清理"""
    r = _get_redis()
    if r:
        try:
            r.delete(f'hand:{hand_id}')
            return
        except Exception:
            pass
    _memory_store.pop(f'hand:{hand_id}', None)


# ── 通用 KV 缓存（用于统计缓存等）────────────────────────

def cache_set(key: str, value, ttl: int = 300):
    data = json.dumps(value).encode()
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl, data)
            return
        except Exception:
            pass
    _memory_store[key] = data


def cache_get(key: str) -> Optional[object]:
    r = _get_redis()
    if r:
        try:
            data = r.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
    data = _memory_store.get(key)
    return json.loads(data) if data else None


def cache_delete(key: str):
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass
    _memory_store.pop(key, None)


def is_redis_connected() -> bool:
    return _get_redis() is not None
