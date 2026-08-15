# -*- coding: utf-8 -*-
"""SSE streaming helpers for Phase 3."""
import asyncio
import json
import logging

from fastapi.responses import StreamingResponse

from . import async_redis, channel_manager, config, metrics

_logger = logging.getLogger(__name__)

SSE_HEADERS = {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-store',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
}


def _meta_truthy(meta, key):
    val = (meta or {}).get(key)
    if val is None:
        return None
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def _format_sse(event, data, event_id=None):
    lines = []
    if event_id is not None:
        lines.append('id: %s' % event_id)
    if event:
        lines.append('event: %s' % event)
    if isinstance(data, (dict, list)):
        payload = json.dumps(data, separators=(',', ':'))
    else:
        payload = data if data is not None else ''
    for part in str(payload).splitlines() or ['']:
        lines.append('data: %s' % part)
    lines.append('')
    return '\n'.join(lines) + '\n'


async def _check_lb_protection(dbname, tid):
    """Option A. Returns (ok, early_response_or_None).

    ok=False with response means do not stream full snapshot.
    """
    meta, err = await async_redis.get_meta(dbname, tid)
    if err == 'error':
        return False, StreamingResponse(
            iter([_format_sse('error', {'error': 'redis'})]),
            status_code=503,
            headers=SSE_HEADERS,
            media_type='text/event-stream',
        )
    active = _meta_truthy(meta, 'live_board_active')
    protected = _meta_truthy(meta, 'code_protected')
    if active is None or protected is None:
        # Missing meta → fall back (404) so Nginx/browser use Odoo
        return False, StreamingResponse(
            iter([]),
            status_code=404,
            headers=SSE_HEADERS,
            media_type='text/event-stream',
        )
    if not active:
        body = _format_sse('snapshot', {'live_board_active': False}, event_id=0)

        async def _once():
            yield body

        return False, StreamingResponse(
            _once(),
            status_code=200,
            headers=SSE_HEADERS,
            media_type='text/event-stream',
        )
    if protected:
        return False, StreamingResponse(
            iter([]),
            status_code=404,
            headers=SSE_HEADERS,
            media_type='text/event-stream',
        )
    return True, None


async def sse_stream(dbname, slug, kind, last_event_id=None):
    """Async generator for one SSE client (protection already checked)."""
    if kind not in ('lb', 'pj', 'bal'):
        return

    tid, err = await async_redis.resolve_tid(dbname, slug)
    if err == 'error' or tid is None:
        metrics.incr_sse('sse_fallbacks')
        yield _format_sse('error', {'error': 'miss' if tid is None else 'redis'})
        return

    ch, queue = await channel_manager.manager.join(dbname, tid, kind)
    last_sent = -1
    if last_event_id is not None:
        try:
            last_sent = int(last_event_id)
            metrics.incr_sse('sse_reconnects')
        except (TypeError, ValueError):
            last_sent = -1

    try:
        # Race fix: already subscribed via join(); now read snapshot.
        raw, serr = await async_redis.get_raw_snapshot(dbname, tid, kind)
        if serr == 'error' or serr == 'bad':
            metrics.incr_sse('sse_redis_errors')
            yield _format_sse('error', {'error': 'redis'})
            return
        if raw is None:
            metrics.incr_sse('sse_fallbacks')
            yield _format_sse('error', {'error': 'miss'})
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            metrics.incr_sse('sse_redis_errors')
            yield _format_sse('error', {'error': 'bad'})
            return

        snap_seq = payload.get('seq')
        if snap_seq is None:
            seq_val, _ = await async_redis.get_seq(dbname, tid)
            snap_seq = seq_val if seq_val is not None else 0
        snap_seq = int(snap_seq)

        yield _format_sse('snapshot', payload, event_id=snap_seq)
        metrics.incr_sse('sse_snapshot_sent')
        last_sent = max(last_sent, snap_seq)

        heartbeat = float(getattr(config, 'SSE_HEARTBEAT_SECONDS', 15.0) or 15.0)

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except asyncio.TimeoutError:
                yield ': heartbeat\n\n'
                metrics.incr_sse('sse_heartbeat_sent')
                continue

            if event.get('_error'):
                metrics.incr_sse('sse_redis_errors')
                yield _format_sse('error', {'error': 'redis'})
                break

            targets = event.get('targets') or []
            if kind not in targets:
                continue
            ev_seq = event.get('seq')
            if ev_seq is None:
                continue
            try:
                ev_seq = int(ev_seq)
            except (TypeError, ValueError):
                continue
            if ev_seq <= last_sent:
                continue

            raw2, serr2 = await async_redis.get_raw_snapshot(dbname, tid, kind)
            if serr2 or raw2 is None:
                metrics.incr_sse('sse_redis_errors')
                continue
            try:
                payload2 = json.loads(raw2)
            except json.JSONDecodeError:
                metrics.incr_sse('sse_redis_errors')
                continue
            yield _format_sse('auction.update', payload2, event_id=ev_seq)
            metrics.incr_sse('sse_events_sent')
            last_sent = ev_seq
    finally:
        await channel_manager.manager.leave(dbname, tid, kind, queue)


async def make_sse_response(dbname, slug, kind, last_event_id=None):
    """Build StreamingResponse, applying LB Option A before streaming."""
    if not config.valid_db(dbname) or not config.valid_slug(slug):
        return StreamingResponse(
            iter([]), status_code=404, headers=SSE_HEADERS,
            media_type='text/event-stream',
        )

    tid, err = await async_redis.resolve_tid(dbname, slug)
    if err == 'error':
        metrics.incr_sse('sse_fallbacks')
        return StreamingResponse(
            iter([_format_sse('error', {'error': 'redis'})]),
            status_code=503, headers=SSE_HEADERS,
            media_type='text/event-stream',
        )
    if tid is None:
        metrics.incr_sse('sse_fallbacks')
        return StreamingResponse(
            iter([]), status_code=404, headers=SSE_HEADERS,
            media_type='text/event-stream',
        )

    if kind == 'lb':
        ok, early = await _check_lb_protection(dbname, tid)
        if not ok:
            metrics.incr_sse('sse_fallbacks')
            return early

    gen = sse_stream(dbname, slug, kind, last_event_id=last_event_id)
    return StreamingResponse(
        gen,
        status_code=200,
        headers=SSE_HEADERS,
        media_type='text/event-stream',
    )
