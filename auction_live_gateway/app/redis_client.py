# -*- coding: utf-8 -*-
"""Redis client for the Phase 2B gateway. Fail-fast timeouts. No Odoo."""
import json
import logging
import os
import threading
from urllib.parse import unquote, urlparse

import redis

from . import config

_logger = logging.getLogger(__name__)
_lock = threading.Lock()
_client = None
_client_url = None


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


def reset():
    global _client, _client_url
    with _lock:
        _client = None
        _client_url = None


def get_client():
    global _client, _client_url
    url = config.REDIS_URL
    with _lock:
        if _client is not None and _client_url == url:
            return _client
        try:
            kw = _parse_uri(url)
            # Pool so concurrent ASGI requests do not serialize on one socket.
            pool = redis.ConnectionPool(
                max_connections=int(os.environ.get('AUCTION_REDIS_MAX_CONNECTIONS', '64')),
                **kw
            )
            client = redis.Redis(connection_pool=pool)
            client.ping()
            _client = client
            _client_url = url
            return client
        except Exception as err:
            _logger.warning('gateway redis connect failed: %s', err)
            _client = None
            _client_url = None
            return None


def ping():
    client = get_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        reset()
        return False


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
    }


def resolve_tid(dbname, slug):
    """Return (tid, None) or (None, 'miss'|'error')."""
    client = get_client()
    if client is None:
        return None, 'error'
    try:
        raw = client.get(slug_tid_key(dbname, slug))
        if raw is None:
            return None, 'miss'
        return int(raw), None
    except Exception as err:
        _logger.warning('gateway resolve_tid failed: %s', err)
        reset()
        return None, 'error'


def get_meta(dbname, tid):
    client = get_client()
    if client is None:
        return None, 'error'
    try:
        data = client.hgetall(tid_keys(dbname, tid)['meta']) or {}
        return data, None
    except Exception as err:
        _logger.warning('gateway get_meta failed: %s', err)
        reset()
        return None, 'error'


def get_raw_snapshot(dbname, tid, kind):
    """Return (json_str, None) or (None, 'miss'|'error'|'bad')."""
    if kind not in ('lb', 'pj', 'bal'):
        return None, 'miss'
    client = get_client()
    if client is None:
        return None, 'error'
    try:
        raw = client.get(tid_keys(dbname, tid)[kind])
        if raw is None:
            return None, 'miss'
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        # Validate JSON without rebuilding business payload
        json.loads(raw)
        return raw, None
    except json.JSONDecodeError:
        return None, 'bad'
    except Exception as err:
        _logger.warning('gateway get_snapshot failed: %s', err)
        reset()
        return None, 'error'
