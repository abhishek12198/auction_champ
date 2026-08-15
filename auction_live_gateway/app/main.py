# -*- coding: utf-8 -*-
"""Phase 2B Redis read gateway.

Browser → Nginx → this process → Redis.
Never imports Odoo. Never opens PostgreSQL.
On miss/error return 404/503 so Nginx falls back to Odoo.
"""
import json
import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from . import config, metrics, redis_client

_logger = logging.getLogger(__name__)

app = FastAPI(title='AuctionChamp Live Gateway', docs_url=None, redoc_url=None)


def _json_headers():
    return {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
    }


def _miss():
    metrics.incr('redis_miss')
    metrics.incr('fallback')
    return Response(status_code=404, headers=_json_headers())


def _error():
    metrics.incr('redis_error')
    metrics.incr('fallback')
    return Response(status_code=503, headers=_json_headers())


def _validate(db, slug):
    if not config.valid_db(db) or not config.valid_slug(slug):
        return False
    if len(db) + len(slug) > config.MAX_PATH_LEN:
        return False
    return True


def _meta_truthy(meta, key):
    val = (meta or {}).get(key)
    if val is None:
        return None
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def _serve_kind(db, slug, kind, wrap_jsonrpc=False):
    t0 = metrics.timed()
    if not _validate(db, slug):
        metrics.incr('fallback', latency_ms=(metrics.timed() - t0) * 1000)
        return Response(status_code=404, headers=_json_headers())

    tid, err = redis_client.resolve_tid(db, slug)
    if err == 'error':
        return _error()
    if tid is None:
        return _miss()

    # Live Board Option A: inactive / code-protected → fall back to Odoo
    if kind == 'lb':
        meta, merr = redis_client.get_meta(db, tid)
        if merr == 'error':
            return _error()
        active = _meta_truthy(meta, 'live_board_active')
        protected = _meta_truthy(meta, 'code_protected')
        # Missing meta: fail open to Odoo (do not guess unlocked)
        if active is None or protected is None:
            return _miss()
        if not active:
            # Mirror Odoo inactive response without serving full snapshot
            body = json.dumps({'live_board_active': False})
            metrics.incr('redis_hit', latency_ms=(metrics.timed() - t0) * 1000)
            return Response(content=body, status_code=200, headers=_json_headers())
        if protected:
            # Do not bypass code lock — Nginx → Odoo unlock/cookie path
            return _miss()

    raw, serr = redis_client.get_raw_snapshot(db, tid, kind)
    if serr == 'error' or serr == 'bad':
        return _error()
    if raw is None:
        return _miss()

    # Pre-tracker Bid Summary snapshots have teams only. Fall back to Odoo
    # so it rebuilds Redis with Sold/Unsold/In-auction player lists.
    if kind == 'bal':
        try:
            bal = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return _error()
        if not isinstance(bal, dict) or not isinstance(bal.get('players'), dict):
            return _miss()
        bags = bal.get('players') or {}
        for bucket in ('sold', 'unsold', 'auction'):
            rows = bags.get(bucket) or []
            if rows and (not isinstance(rows[0], dict) or 'attrs' not in rows[0]):
                return _miss()
            for row in rows[:8]:
                photo = row.get('photo_url') or ''
                if photo and 'sz=bs' not in photo and 'default_icon' not in photo:
                    return _miss()

    if wrap_jsonrpc:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return _error()
        body = json.dumps({
            'jsonrpc': '2.0',
            'id': None,
            'result': payload,
        }, separators=(',', ':'))
    else:
        body = raw

    metrics.incr('redis_hit', latency_ms=(metrics.timed() - t0) * 1000)
    _logger.debug(
        'hit kind=%s db=%s slug=%s tid=%s bytes=%s',
        kind, db, slug, tid, len(body),
    )
    return Response(content=body, status_code=200, headers=_json_headers())


@app.get('/health')
def health():
    return PlainTextResponse('ok')


@app.get('/ready')
def ready():
    if redis_client.ping():
        return PlainTextResponse('ready')
    return PlainTextResponse('redis unavailable', status_code=503)


@app.get('/metrics')
def metrics_endpoint():
    return JSONResponse(metrics.snapshot())


@app.get('/{db}/{slug}/auction/live-board/data')
def live_board(db: str, slug: str):
    return _serve_kind(db, slug, 'lb', wrap_jsonrpc=False)


@app.get('/{db}/{slug}/auction/show/team/balance/json')
def bid_summary(db: str, slug: str):
    return _serve_kind(db, slug, 'bal', wrap_jsonrpc=False)


@app.post('/{db}/auction/projector/{slug}/data')
async def projector(db: str, slug: str, request: Request):
    # Body ignored — Redis already holds the final projector snapshot.
    # Accept POST so existing frontend JSON-RPC calls keep working.
    _ = await request.body()
    return _serve_kind(db, slug, 'pj', wrap_jsonrpc=True)


# ── Phase 3 SSE ──────────────────────────────────────────────────────────────

@app.get('/{db}/{slug}/auction/live-board/events')
async def live_board_events(db: str, slug: str, request: Request):
    from . import sse as sse_mod
    last_id = request.headers.get('last-event-id')
    return await sse_mod.make_sse_response(db, slug, 'lb', last_event_id=last_id)


@app.get('/{db}/auction/projector/{slug}/events')
async def projector_events(db: str, slug: str, request: Request):
    from . import sse as sse_mod
    last_id = request.headers.get('last-event-id')
    return await sse_mod.make_sse_response(db, slug, 'pj', last_event_id=last_id)


@app.get('/{db}/{slug}/auction/show/team/balance/events')
async def balance_events(db: str, slug: str, request: Request):
    from . import sse as sse_mod
    last_id = request.headers.get('last-event-id')
    return await sse_mod.make_sse_response(db, slug, 'bal', last_event_id=last_id)
