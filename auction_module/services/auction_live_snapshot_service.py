# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################
"""Build and serve live-auction snapshots.

PostgreSQL ``auction_tournament.live_snapshot_seq`` is the authority.
Redis holds a shared replica of already-committed poll JSON. If Redis is
disabled, down, stale, or behind, callers fall back to the existing ORM
builders. Per-worker ``_LIVE_PAYLOAD_CACHE`` remains a tertiary shortcut
on the ORM path only — it cannot be correct across workers or after a
mutation on another process.
"""
import logging
import time

from odoo.addons.auction_module.services import auction_redis_service as redis_svc
from odoo.addons.auction_module.services import auction_live_payload as payload_svc

_logger = logging.getLogger(__name__)

KIND_BUILDERS = {
    'lb': 'live',
    'pj': 'projector',
    'bal': 'balance',
}


def _pg_seq(tournament):
    try:
        return int(tournament.live_snapshot_seq or 0)
    except Exception:
        return 0


def build_live_snapshot(env, tournament, db_name, seq):
    t0 = time.monotonic()
    data = payload_svc.build_live_board_payload(env, tournament, db_name)
    data = payload_svc.attach_seq(data, seq)
    _logger.debug(
        'auction snapshot build lb tid=%s seq=%s in %.1fms',
        tournament.id, seq, (time.monotonic() - t0) * 1000,
    )
    return data


def build_projector_snapshot(env, tournament, db_name, seq):
    t0 = time.monotonic()
    data = payload_svc.build_projector_payload(env, tournament, db_name)
    data = payload_svc.attach_seq(data, seq)
    _logger.debug(
        'auction snapshot build pj tid=%s seq=%s in %.1fms',
        tournament.id, seq, (time.monotonic() - t0) * 1000,
    )
    return data


def build_balance_snapshot(env, tournament, seq):
    t0 = time.monotonic()
    data = payload_svc.build_balance_payload(env, tournament)
    data = payload_svc.attach_seq(data, seq)
    _logger.debug(
        'auction snapshot build bal tid=%s seq=%s in %.1fms',
        tournament.id, seq, (time.monotonic() - t0) * 1000,
    )
    return data


def _build_kind(env, tournament, kind, seq):
    db_name = env.cr.dbname
    if kind == 'lb':
        return build_live_snapshot(env, tournament, db_name, seq)
    if kind == 'pj':
        return build_projector_snapshot(env, tournament, db_name, seq)
    if kind == 'bal':
        return build_balance_snapshot(env, tournament, seq)
    return None


def write_snapshots_to_redis(env, tournament_id, seq, snapshots):
    """Write snapshots + gateway meta; self-heal slug→tid. Never raises."""
    tournament = env['auction.tournament'].sudo().browse(int(tournament_id))
    meta = {
        'seq': seq,
        'kinds': ','.join(sorted(k for k in snapshots if snapshots.get(k) is not None)),
        'live_board_active': (
            '1' if tournament.exists() and tournament.live_board_active else '0'
        ),
        'code_protected': (
            '1' if tournament.exists() and tournament.live_board_code_protected else '0'
        ),
        'slug': (tournament.slug or '') if tournament.exists() else '',
    }
    ok = redis_svc.write_snapshots(env, tournament_id, seq, snapshots, meta=meta)
    # Self-heal Phase 2B slug map after a successful snapshot write.
    if ok and tournament.exists() and tournament.slug:
        redis_svc.set_slug_tid(env, tournament.slug, tournament.id)
    # Phase 3: publish invalidation only after CAS succeeded and snapshots exist.
    if ok:
        targets = [k for k in ('lb', 'pj', 'bal') if snapshots.get(k) is not None]
        try:
            redis_svc.publish_tournament_event(env, tournament_id, seq, targets)
        except Exception:
            _logger.debug('auction redis publish skipped', exc_info=True)
    return ok


def rebuild_tournament_snapshots(env, tournament_id, snapshot_seq, snapshot_types):
    """Rebuild selected snapshot kinds from committed PostgreSQL state.

    Called from postcommit (new cursor) or from a poll cache-miss rebuild.
    Never raises: Redis/build errors are logged.
    """
    try:
        tournament = env['auction.tournament'].sudo().browse(int(tournament_id))
        if not tournament.exists():
            return False
        if snapshot_seq is None:
            snapshot_seq = _pg_seq(tournament)
        kinds = set(snapshot_types or ('lb', 'pj', 'bal'))
        snapshots = {}
        for kind in ('lb', 'pj', 'bal'):
            if kind not in kinds:
                continue
            snapshots[kind] = _build_kind(env, tournament, kind, snapshot_seq)
        if not snapshots:
            return False
        write_snapshots_to_redis(env, tournament.id, snapshot_seq, snapshots)
        return True
    except Exception:
        _logger.warning(
            'auction snapshot rebuild failed tid=%s seq=%s',
            tournament_id, snapshot_seq, exc_info=True,
        )
        return False


def _snapshot_schema_ok(kind, payload):
    """Reject stale `bal` JSON so Bid Summary rebuilds player lists/attrs."""
    if not payload or not isinstance(payload, dict):
        return False
    if kind == 'bal':
        players = payload.get('players')
        if not isinstance(players, dict):
            return False
        for bucket in ('sold', 'unsold', 'auction'):
            rows = players.get(bucket) or []
            if rows and not isinstance(rows[0], dict):
                return False
            if rows and 'attrs' not in rows[0]:
                return False
            for row in rows[:8]:
                photo = row.get('photo_url') or ''
                if photo and 'sz=bs' not in photo and 'default_icon' not in photo:
                    return False
    return True


def _redis_fresh(env, tournament, kind, pg_seq):
    redis_seq = redis_svc.get_seq(env, tournament.id)
    # Missing key only — seq 0 is a valid committed version.
    if redis_seq is None:
        return None
    if int(redis_seq) != int(pg_seq):
        return None
    payload = redis_svc.get_snapshot(env, tournament.id, kind)
    if payload is None:
        return None
    payload_seq = payload.get('seq')
    if payload_seq is None:
        return None
    if int(payload_seq) != int(pg_seq):
        return None
    if not _snapshot_schema_ok(kind, payload):
        return None
    return payload


def _tertiary_cache_get(kind, tournament):
    """Process-local fingerprint cache. Not correct across workers — Redis is."""
    try:
        from odoo.addons.auction_module.controllers.main import _live_payload_get
        cached = _live_payload_get(kind, tournament)
        if cached is None:
            return None
        if isinstance(cached, (bytes, str)):
            import json
            if isinstance(cached, bytes):
                cached = cached.decode('utf-8')
            cached = json.loads(cached)
        return cached
    except Exception:
        _logger.debug('auction snapshot tertiary cache get failed', exc_info=True)
        return None


def _tertiary_cache_put(kind, tournament, payload):
    try:
        from odoo.addons.auction_module.controllers.main import _live_payload_put
        if kind == 'lb':
            import json
            _live_payload_put(kind, tournament, json.dumps(payload))
        else:
            _live_payload_put(kind, tournament, payload)
    except Exception:
        _logger.debug('auction snapshot tertiary cache put failed', exc_info=True)


def get_or_rebuild_snapshot(env, tournament, kind):
    """Poll-path helper: Redis hit if seq matches PG, else rebuild or ORM.

    Returns a dict payload. Never raises Redis errors.
    """
    if not tournament:
        return None
    pg_seq = _pg_seq(tournament)
    if redis_svc.is_enabled(env):
        try:
            hit = _redis_fresh(env, tournament, kind, pg_seq)
            if hit is not None:
                return hit
            if redis_svc.acquire_rebuild_lock(env, tournament.id):
                try:
                    # Re-check after lock: another worker may have filled Redis.
                    hit = _redis_fresh(env, tournament, kind, pg_seq)
                    if hit is not None:
                        return hit
                    t0 = time.monotonic()
                    payload = _build_kind(env, tournament, kind, pg_seq)
                    write_snapshots_to_redis(
                        env, tournament.id, pg_seq, {kind: payload},
                    )
                    _tertiary_cache_put(kind, tournament, payload)
                    _logger.debug(
                        'auction snapshot rebuild-lock %s tid=%s seq=%s in %.1fms',
                        kind, tournament.id, pg_seq,
                        (time.monotonic() - t0) * 1000,
                    )
                    return payload
                finally:
                    redis_svc.release_rebuild_lock(env, tournament.id)
            waited = redis_svc.wait_for_snapshot(
                env, tournament.id, kind, pg_seq,
            )
            if waited is not None and _snapshot_schema_ok(kind, waited):
                return waited
        except Exception:
            _logger.warning(
                'auction snapshot redis path failed tid=%s kind=%s; ORM fallback',
                tournament.id, kind, exc_info=True,
            )
    cached = _tertiary_cache_get(kind, tournament)
    if cached is not None and _snapshot_schema_ok(kind, cached):
        return payload_svc.attach_seq(cached, pg_seq) if 'seq' not in cached else cached
    t0 = time.monotonic()
    payload = _build_kind(env, tournament, kind, pg_seq)
    _tertiary_cache_put(kind, tournament, payload)
    _logger.debug(
        'auction snapshot ORM fallback %s tid=%s in %.1fms',
        kind, tournament.id, (time.monotonic() - t0) * 1000,
    )
    return payload
