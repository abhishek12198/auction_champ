# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################
"""Optional Redis client for live-auction snapshots.

PostgreSQL remains the source of truth. Redis is a shared replica of already
committed poll payloads. Import/connection/command failures are never fatal.
"""
import logging
import threading
import time
from urllib.parse import unquote, urlparse

_logger = logging.getLogger(__name__)

PARAM_ENABLED = 'auction.redis.enabled'
PARAM_URI = 'auction.redis.uri'
DEFAULT_URI = 'redis://127.0.0.1:6379/1'
CONNECT_TIMEOUT = 0.05
SOCKET_TIMEOUT = 0.1
REBUILD_LOCK_TTL = 5

# Atomic compare-and-set: never let an older postcommit overwrite a newer seq.
# KEYS: seq, lb, pj, bal, meta
# ARGV: incoming_seq, lb_json|'', pj_json|'', bal_json|'',
#       meta field count, then field/value pairs
_CAS_LUA = """
local seq_key = KEYS[1]
local incoming = tonumber(ARGV[1])
if incoming == nil then
    return 0
end
local current = tonumber(redis.call('GET', seq_key) or '-1')
if incoming < current then
    return 0
end
if ARGV[2] ~= '' then
    redis.call('SET', KEYS[2], ARGV[2])
end
if ARGV[3] ~= '' then
    redis.call('SET', KEYS[3], ARGV[3])
end
if ARGV[4] ~= '' then
    redis.call('SET', KEYS[4], ARGV[4])
end
local nmeta = tonumber(ARGV[5]) or 0
if nmeta > 0 then
    redis.call('DEL', KEYS[5])
    local i = 0
    while i < nmeta do
        local fk = ARGV[6 + (i * 2)]
        local fv = ARGV[7 + (i * 2)]
        redis.call('HSET', KEYS[5], fk, fv)
        i = i + 1
    end
end
redis.call('SET', seq_key, incoming)
return 1
"""

_pool_lock = threading.Lock()
_client = None
_client_uri = None
_redis_mod = None
_redis_import_failed = False
_last_fail_at = 0.0
_FAIL_COOLDOWN = 2.0


def _try_import_redis():
    global _redis_mod, _redis_import_failed
    if _redis_mod is not None:
        return _redis_mod
    if _redis_import_failed:
        return None
    try:
        import redis as redis_mod  # optional; never required to run auctions
        _redis_mod = redis_mod
        return _redis_mod
    except ImportError:
        _redis_import_failed = True
        _logger.debug('auction redis: python package not installed; ORM fallback')
        return None


def parse_redis_uri(uri):
    """Return kwargs for Redis() from redis:// or unix:// URIs."""
    uri = (uri or DEFAULT_URI).strip()
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
            'socket_connect_timeout': CONNECT_TIMEOUT,
            'socket_timeout': SOCKET_TIMEOUT,
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
        'socket_connect_timeout': CONNECT_TIMEOUT,
        'socket_timeout': SOCKET_TIMEOUT,
        'protocol': 2,
    }


def reset_client(mark_failure=False):
    """Drop the worker-local client (tests / reconnect)."""
    global _client, _client_uri, _last_fail_at
    with _pool_lock:
        _client = None
        _client_uri = None
        if mark_failure:
            _last_fail_at = time.monotonic()
        else:
            _last_fail_at = 0.0


def _params_from_env(env):
    ICP = env['ir.config_parameter'].sudo()
    enabled = (ICP.get_param(PARAM_ENABLED, 'False') or '').strip().lower()
    uri = (ICP.get_param(PARAM_URI, DEFAULT_URI) or DEFAULT_URI).strip()
    return enabled in ('1', 'true', 'yes', 'on'), uri


def is_enabled(env):
    try:
        enabled, _uri = _params_from_env(env)
        return enabled
    except Exception:
        _logger.debug('auction redis: enabled check failed', exc_info=True)
        return False


def get_client(env, ping=False):
    """Return a worker-local Redis client or None.

    Never raises. Missing package, disabled config, or dead server → None.
    Ping only when opening a new connection so viewer polls are not noisy.
    """
    global _client, _client_uri, _last_fail_at
    redis_mod = _try_import_redis()
    if redis_mod is None:
        return None
    if _last_fail_at and (time.monotonic() - _last_fail_at) < _FAIL_COOLDOWN:
        return None
    try:
        enabled, uri = _params_from_env(env)
    except Exception:
        _logger.debug('auction redis: config read failed', exc_info=True)
        return None
    if not enabled:
        return None
    with _pool_lock:
        if _client is not None and _client_uri == uri:
            return _client
        try:
            t0 = time.monotonic()
            client = redis_mod.Redis(**parse_redis_uri(uri))
            client.ping()
            _client = client
            _client_uri = uri
            _last_fail_at = 0.0
            _logger.debug(
                'auction redis: connected uri=%s in %.1fms',
                uri, (time.monotonic() - t0) * 1000,
            )
            return client
        except Exception as err:
            _logger.warning('auction redis: connect/ping failed: %s', err)
            _client = None
            _client_uri = None
            _last_fail_at = time.monotonic()
            return None


def key_prefix(dbname, tournament_id):
    return 'ac:%s:t:%s' % (dbname, int(tournament_id))


def keys_for(dbname, tournament_id):
    prefix = key_prefix(dbname, tournament_id)
    return {
        'lb': '%s:lb' % prefix,
        'pj': '%s:pj' % prefix,
        'bal': '%s:bal' % prefix,
        'meta': '%s:meta' % prefix,
        'seq': '%s:seq' % prefix,
        'lock': '%s:rebuild_lock' % prefix,
        'events': '%s:events' % prefix,
    }


def events_channel(dbname, tournament_id):
    """Pub/Sub channel for Phase 3 SSE invalidation events."""
    return keys_for(dbname, tournament_id)['events']


def publish_tournament_event(env, tournament_id, seq, targets, event='auction.update'):
    """Publish a small invalidation event after a successful snapshot CAS.

    Never raises. Redis failure must not affect auction transactions.
    """
    client = get_client(env, ping=False)
    if client is None:
        return False
    import json
    dbname = env.cr.dbname
    payload = {
        'event': event or 'auction.update',
        'db': dbname,
        'tournament_id': int(tournament_id),
        'seq': int(seq),
        'targets': sorted(t for t in (targets or []) if t in ('lb', 'pj', 'bal')),
        'ts': time.time(),
    }
    if not payload['targets']:
        return False
    try:
        channel = events_channel(dbname, tournament_id)
        client.publish(channel, json.dumps(payload, separators=(',', ':')))
        return True
    except Exception as err:
        _logger.warning(
            'auction redis: PUBLISH failed tid=%s seq=%s: %s',
            tournament_id, seq, err,
        )
        return False


def slug_tid_key(dbname, slug):
    """Redis key: slug → tournament id (for Phase 2B gateway; no PG)."""
    return 'ac:%s:slug:%s:tid' % (dbname, slug)


def set_slug_tid(env, slug, tournament_id, old_slug=None):
    """Write slug→tid map. Never raises; Redis failure is logged only."""
    slug = (slug or '').strip()
    if not slug or not tournament_id:
        return False
    client = get_client(env, ping=False)
    if client is None:
        return False
    dbname = env.cr.dbname
    try:
        if old_slug and old_slug != slug:
            client.delete(slug_tid_key(dbname, old_slug))
        client.set(slug_tid_key(dbname, slug), int(tournament_id))
        return True
    except Exception as err:
        _logger.warning('auction redis: slug map set failed: %s', err)
        reset_client(mark_failure=True)
        return False


def delete_slug_tid(env, slug):
    slug = (slug or '').strip()
    if not slug:
        return False
    client = get_client(env, ping=False)
    if client is None:
        return False
    try:
        client.delete(slug_tid_key(env.cr.dbname, slug))
        return True
    except Exception as err:
        _logger.warning('auction redis: slug map delete failed: %s', err)
        reset_client(mark_failure=True)
        return False


def get_slug_tid(env, slug):
    slug = (slug or '').strip()
    if not slug:
        return None
    client = get_client(env)
    if client is None:
        return None
    try:
        raw = client.get(slug_tid_key(env.cr.dbname, slug))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return int(raw)
    except Exception as err:
        _logger.warning('auction redis: slug map get failed: %s', err)
        reset_client(mark_failure=True)
        return None


def get_seq(env, tournament_id):
    client = get_client(env)
    if client is None:
        return None
    keys = keys_for(env.cr.dbname, tournament_id)
    try:
        t0 = time.monotonic()
        raw = client.get(keys['seq'])
        _logger.debug(
            'auction redis GET seq tid=%s in %.1fms',
            tournament_id, (time.monotonic() - t0) * 1000,
        )
        if raw is None:
            return None
        return int(raw)
    except Exception as err:
        _logger.warning('auction redis: GET seq failed: %s', err)
        reset_client(mark_failure=True)
        return None


def get_snapshot(env, tournament_id, kind):
    """Return decoded JSON dict for kind in ('lb','pj','bal'), or None."""
    if kind not in ('lb', 'pj', 'bal'):
        return None
    client = get_client(env)
    if client is None:
        return None
    keys = keys_for(env.cr.dbname, tournament_id)
    try:
        t0 = time.monotonic()
        raw = client.get(keys[kind])
        _logger.debug(
            'auction redis GET %s tid=%s in %.1fms',
            kind, tournament_id, (time.monotonic() - t0) * 1000,
        )
        if not raw:
            return None
        import json
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw)
    except Exception as err:
        _logger.warning('auction redis: GET %s failed: %s', kind, err)
        reset_client(mark_failure=True)
        return None


def write_snapshots(env, tournament_id, seq, snapshots, meta=None):
    """Atomically write snapshots if incoming seq >= stored seq.

    ``snapshots`` is a dict with optional keys lb/pj/bal (JSON-serializable).
    Returns True if written, False if rejected/unavailable. Never raises.
    """
    client = get_client(env)
    if client is None:
        return False
    import json
    keys = keys_for(env.cr.dbname, tournament_id)
    lb = json.dumps(snapshots['lb'], separators=(',', ':')) if snapshots.get('lb') is not None else ''
    pj = json.dumps(snapshots['pj'], separators=(',', ':')) if snapshots.get('pj') is not None else ''
    bal = json.dumps(snapshots['bal'], separators=(',', ':')) if snapshots.get('bal') is not None else ''
    meta = meta or {}
    meta_args = []
    for mk, mv in meta.items():
        meta_args.extend([str(mk), '' if mv is None else str(mv)])
    argv = [int(seq), lb, pj, bal, len(meta)] + meta_args
    try:
        t0 = time.monotonic()
        ok = client.eval(
            _CAS_LUA,
            5,
            keys['seq'], keys['lb'], keys['pj'], keys['bal'], keys['meta'],
            *argv
        )
        _logger.debug(
            'auction redis CAS seq=%s tid=%s ok=%s in %.1fms',
            seq, tournament_id, ok, (time.monotonic() - t0) * 1000,
        )
        return bool(ok)
    except Exception as err:
        _logger.warning(
            'auction redis: atomic write failed tid=%s seq=%s: %s',
            tournament_id, seq, err,
        )
        reset_client(mark_failure=True)
        return False


def acquire_rebuild_lock(env, tournament_id, token='1'):
    """SET NX rebuild lock. Returns True if this worker owns the rebuild."""
    client = get_client(env, ping=False)
    if client is None:
        return False
    keys = keys_for(env.cr.dbname, tournament_id)
    try:
        t0 = time.monotonic()
        got = client.set(keys['lock'], token, nx=True, ex=REBUILD_LOCK_TTL)
        _logger.debug(
            'auction redis lock tid=%s got=%s in %.1fms',
            tournament_id, bool(got), (time.monotonic() - t0) * 1000,
        )
        return bool(got)
    except Exception:
        _logger.warning('auction redis: lock failed', exc_info=True)
        return False


def release_rebuild_lock(env, tournament_id):
    client = get_client(env, ping=False)
    if client is None:
        return
    keys = keys_for(env.cr.dbname, tournament_id)
    try:
        client.delete(keys['lock'])
    except Exception:
        _logger.debug('auction redis: lock release failed', exc_info=True)


def wait_for_snapshot(env, tournament_id, kind, expected_seq, attempts=4, delay=0.05):
    """Brief wait for another worker's rebuild. Returns payload or None."""
    for _ in range(max(1, attempts)):
        stored = get_seq(env, tournament_id)
        if stored is not None and int(stored) >= int(expected_seq):
            payload = get_snapshot(env, tournament_id, kind)
            if payload is None:
                time.sleep(delay)
                continue
            payload_seq = payload.get('seq')
            # seq 0 is valid; only missing seq is a miss
            if payload_seq is not None and int(payload_seq) >= int(expected_seq):
                return payload
        time.sleep(delay)
    return None
