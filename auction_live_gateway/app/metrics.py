# -*- coding: utf-8 -*-
"""Lightweight process counters (no per-request INFO spam)."""
import threading
import time

_lock = threading.Lock()
_counters = {
    'redis_hit': 0,
    'redis_miss': 0,
    'redis_error': 0,
    'fallback': 0,
    'requests': 0,
    'latency_ms_sum': 0.0,
    # Phase 3 SSE
    'sse_connections_total': 0,
    'sse_connections_current': 0,
    'sse_disconnects': 0,
    'sse_reconnects': 0,
    'sse_events_sent': 0,
    'sse_snapshot_sent': 0,
    'sse_heartbeat_sent': 0,
    'sse_redis_subscriptions': 0,
    'sse_redis_errors': 0,
    'sse_fallbacks': 0,
}


def incr(name, latency_ms=None):
    with _lock:
        _counters['requests'] = _counters.get('requests', 0) + 1
        if name in _counters:
            _counters[name] += 1
        if latency_ms is not None:
            _counters['latency_ms_sum'] += float(latency_ms)


def incr_sse(name, n=1):
    """SSE counters — do not bump generic request count for heartbeats."""
    with _lock:
        if name in _counters:
            _counters[name] += int(n)


def sse_gauge(name, delta):
    with _lock:
        if name in _counters:
            _counters[name] = max(0, int(_counters[name]) + int(delta))


def snapshot():
    with _lock:
        data = dict(_counters)
    n = data.get('requests') or 0
    data['latency_ms_avg'] = (
        round(data['latency_ms_sum'] / n, 3) if n else 0.0
    )
    return data


def timed():
    return time.monotonic()
