# -*- coding: utf-8 -*-
"""Async Redis helpers for Phase 3 SSE (Pub/Sub + snapshot GET).

Separate from the sync redis_client used by short /data polls.
"""
import json
import logging
from urllib.parse import unquote, urlparse

import redis.asyncio as aioredis

from . import config

_logger = logging.getLogger(__name__)
_pool = None
_pool_url = None


def _parse_uri(uri):
    uri = (uri or config.REDIS_URL).strip()
    if uri.startswith('unix://'):
        rest = uri[len('unix://'):]
        path, _, query = rest.partition('?')
        db = 0
        password = None
        if query:
            for part in query.split('&'):
                if '=' not in part:
                    continue
                k, v = part.split('=', 1)
                if k == 'db':
                    db = int(v or 0)
                elif k in ('password', 'pass'):
                    password = unquote(v)
        return {
            'unix_socket_path': path or '/var/run/redis/redis.sock',
            'db': db,
            'password': password,
            'socket_connect_timeout': config.CONNECT_TIMEOUT,
            'socket_timeout': config.SOCKET_TIMEOUT,
            'decode_responses': True,
            'protocol': 2,
        }
    parsed = urlparse(uri)
    db = 0
    if parsed.path and parsed.path != '/':
        try:
            db = int(parsed.path.lstrip('/') or 0)
        except ValueError:
            db = 0
    return {
        'host': parsed.hostname or '127.0.0.1',
        'port': parsed.port or 6379,
        'db': db,
        'password': parsed.password,
        'socket_connect_timeout': config.CONNECT_TIMEOUT,
        'socket_timeout': config.SOCKET_TIMEOUT,
        'decode_responses': True,
        'protocol': 2,
    }


async def get_pool():
    global _pool, _pool_url
    url = config.REDIS_URL
    if _pool is not None and _pool_url == url:
        return _pool
    kw = _parse_uri(url)
    _pool = aioredis.ConnectionPool(
        max_connections=int(
            __import__('os').environ.get('AUCTION_REDIS_MAX_CONNECTIONS', '128')
        ),
        **kw
    )
    _pool_url = url
    return _pool


async def get_client():
    pool = await get_pool()
    return aioredis.Redis(connection_pool=pool)


async def reset():
    global _pool, _pool_url
    if _pool is not None:
        try:
            await _pool.disconnect()
        except Exception:
            pass
    _pool = None
    _pool_url = None


def slug_tid_key(dbname, slug):
    return 'ac:%s:slug:%s:tid' % (dbname, slug)


def tid_keys(dbname, tid):
    prefix = 'ac:%s:t:%s' % (dbname, int(tid))
    return {
        'lb': '%s:lb' % prefix,
        'pj': '%s:pj' % prefix,
        'bal': '%s:bal' % prefix,
        'meta': '%s:meta' % prefix,
        'seq': '%s:seq' % prefix,
        'events': '%s:events' % prefix,
    }


async def resolve_tid(dbname, slug):
    try:
        client = await get_client()
        raw = await client.get(slug_tid_key(dbname, slug))
        if raw is None:
            return None, 'miss'
        return int(raw), None
    except Exception as err:
        _logger.warning('async resolve_tid failed: %s', err)
        await reset()
        return None, 'error'


async def get_meta(dbname, tid):
    try:
        client = await get_client()
        data = await client.hgetall(tid_keys(dbname, tid)['meta']) or {}
        return data, None
    except Exception as err:
        _logger.warning('async get_meta failed: %s', err)
        await reset()
        return None, 'error'


async def get_seq(dbname, tid):
    try:
        client = await get_client()
        raw = await client.get(tid_keys(dbname, tid)['seq'])
        if raw is None:
            return None, None
        return int(raw), None
    except Exception as err:
        _logger.warning('async get_seq failed: %s', err)
        await reset()
        return None, 'error'


async def get_raw_snapshot(dbname, tid, kind):
    if kind not in ('lb', 'pj', 'bal'):
        return None, 'miss'
    try:
        client = await get_client()
        raw = await client.get(tid_keys(dbname, tid)[kind])
        if raw is None:
            return None, 'miss'
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        json.loads(raw)  # validate
        return raw, None
    except json.JSONDecodeError:
        return None, 'bad'
    except Exception as err:
        _logger.warning('async get_snapshot failed: %s', err)
        await reset()
        return None, 'error'


async def ping():
    try:
        client = await get_client()
        return bool(await client.ping())
    except Exception:
        await reset()
        return False
