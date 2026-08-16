# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################
"""ORM mutation watcher for live-auction Redis snapshots.

PostgreSQL is authoritative. Watched writes register the tournament on the
current cursor, bump ``live_snapshot_seq`` once per tournament per
transaction, and schedule a single ``cr.postcommit`` callback. Redis is
updated only after COMMIT, on a fresh registry cursor — never on the
request cursor, and never before PostgreSQL commits.

Redis failures are logged and swallowed. Auction mutations always succeed
from the operator's point of view if PostgreSQL committed.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Field → snapshot kinds. Unrelated writes must not dirty Redis.
# BID (current_bid*) is projector-only: live board does not expose the bid.
WATCHED_FIELDS = {
    'auction.team.player': {
        'is_on_stage': frozenset(('lb', 'pj', 'bal')),
        'state': frozenset(('lb', 'pj', 'bal')),
        # BID must refresh Live Board Redis/SSE (not only auctioneer Odoo inject).
        'current_bid': frozenset(('lb', 'pj')),
        'current_bid_team_id': frozenset(('lb', 'pj')),
        'mystery_revealed': frozenset(('lb', 'pj', 'bal')),
        'assigned_team_id': frozenset(('lb', 'pj', 'bal')),
        'photo': frozenset(('lb', 'pj')),
        'name': frozenset(('lb', 'pj', 'bal')),
        'tier_id': frozenset(('lb', 'pj', 'bal')),
        'icon_player': frozenset(('lb', 'pj', 'bal')),
        'role': frozenset(('lb', 'pj', 'bal')),
        'batting_style': frozenset(('lb', 'pj', 'bal')),
        'bowling_style': frozenset(('lb', 'pj', 'bal')),
        'sl_no': frozenset(('lb', 'pj', 'bal')),
        'blood_group': frozenset(('lb', 'pj')),
        'address': frozenset(('lb', 'pj')),
        'age': frozenset(('lb', 'pj', 'bal')),
        'height': frozenset(('lb', 'pj')),
        'weight': frozenset(('lb', 'pj')),
        'dominant_position_id': frozenset(('lb', 'pj', 'bal')),
        'secondary_position_ids': frozenset(('lb', 'pj', 'bal')),
        'preferred_foot': frozenset(('lb', 'pj', 'bal')),
        'work_rate': frozenset(('lb', 'pj', 'bal')),
        'playing_style_ids': frozenset(('lb', 'pj', 'bal')),
        'strength_ids': frozenset(('lb', 'pj', 'bal')),
        'other_attribute_ids': frozenset(('lb', 'pj', 'bal')),
        'contact': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.tournament': {
        'dice_state': frozenset(('pj',)),
        'dice_result': frozenset(('pj',)),
        'break_time_active': frozenset(('lb', 'pj')),
        'stamp_player_id': frozenset(('lb', 'pj')),
        'stamp_state': frozenset(('lb', 'pj')),
        'stamp_expires_at': frozenset(('lb', 'pj')),
        'projector_board_mode': frozenset(('pj',)),
        'projector_board_reveal_until': frozenset(('pj',)),
        'pool_draw_json': frozenset(('pj',)),
        'fixture_schedule_json': frozenset(('pj',)),
        'live_board_active': frozenset(('lb',)),
        'live_board_code_protected': frozenset(('lb',)),
        'auction_declared_complete': frozenset(('lb', 'pj')),
        'name': frozenset(('lb', 'pj')),
        'logo': frozenset(('lb', 'pj')),
        'description': frozenset(('lb', 'pj')),
        'player_display_template': frozenset(('lb', 'pj')),
        'tournament_type': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.team': {
        'name': frozenset(('lb', 'pj', 'bal')),
        'logo': frozenset(('lb', 'pj', 'bal')),
        'manager': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.auction.player': {
        'points': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.auction': {
        'total_point': frozenset(('lb', 'pj', 'bal')),
        'max_players': frozenset(('lb', 'pj', 'bal')),
        'base_point': frozenset(('lb', 'pj', 'bal')),
        'max_limited': frozenset(('lb', 'pj', 'bal')),
        'max_points': frozenset(('lb', 'pj', 'bal')),
        'remaining_points': frozenset(('lb', 'pj', 'bal')),
        'remaining_players_count': frozenset(('lb', 'pj', 'bal')),
        'team_id': frozenset(('lb', 'pj', 'bal')),
        'tournament_id': frozenset(('lb', 'pj', 'bal')),
        'active': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.auction.tier.limit': {
        'max_players': frozenset(('lb', 'pj', 'bal')),
        'base_point': frozenset(('lb', 'pj', 'bal')),
        'max_call': frozenset(('lb', 'pj', 'bal')),
        'tier_id': frozenset(('lb', 'pj', 'bal')),
        'auction_id': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.auction.bid.slab': {
        'from_amount': frozenset(('lb', 'pj', 'bal')),
        'to_amount': frozenset(('lb', 'pj', 'bal')),
        'increment': frozenset(('lb', 'pj', 'bal')),
        'auction_id': frozenset(('lb', 'pj', 'bal')),
    },
    'auction.history': {
        'message': frozenset(('lb', 'pj')),
        'player_photo': frozenset(('lb', 'pj')),
    },
    'auction.advertiser': {
        'name': frozenset(('lb', 'pj')),
        'image': frozenset(('lb', 'pj')),
        'sequence': frozenset(('lb', 'pj')),
        'active': frozenset(('lb', 'pj')),
        'tournament_id': frozenset(('lb', 'pj')),
    },
}

# create/unlink always dirties these models (row presence changes payloads).
WATCH_CREATE_UNLINK = {
    'auction.auction.player': frozenset(('lb', 'pj', 'bal')),
    'auction.history': frozenset(('lb', 'pj')),
    'auction.advertiser': frozenset(('lb', 'pj')),
    'auction.auction.tier.limit': frozenset(('lb', 'pj', 'bal')),
    'auction.auction.bid.slab': frozenset(('lb', 'pj', 'bal')),
    'auction.auction': frozenset(('lb', 'pj', 'bal')),
}


def kinds_for_vals(model_name, vals, create=False, unlink=False):
    """Return snapshot kinds dirtied by this write. Used by tests too."""
    kinds = set()
    if unlink or create:
        kinds.update(WATCH_CREATE_UNLINK.get(model_name, ()))
    watched = WATCHED_FIELDS.get(model_name) or {}
    if vals:
        for field, field_kinds in watched.items():
            if field in vals:
                kinds.update(field_kinds)
    return kinds


def _cursor_state(cr):
    dirty = getattr(cr, '_auction_live_dirty', None)
    if dirty is None:
        cr._auction_live_dirty = dirty = {}
        cr._auction_live_seqs = {}
        cr._auction_live_postcommit = False
    return dirty


def _bump_seq(cr, tournament_id):
    """Increment PostgreSQL live_snapshot_seq once per tournament per cursor.

    PostgreSQL is the authority. Redis INCR is never used as the sequence.
    """
    seqs = cr._auction_live_seqs
    tid = int(tournament_id)
    if tid in seqs:
        return seqs[tid]
    cr.execute(
        """
        UPDATE auction_tournament
           SET live_snapshot_seq = COALESCE(live_snapshot_seq, 0) + 1
         WHERE id = %s
     RETURNING live_snapshot_seq
        """,
        (tid,),
    )
    row = cr.fetchone()
    seq = int(row[0]) if row else 0
    seqs[tid] = seq
    return seq


def _postcommit_rebuild(dbname, dirty, seqs):
    """Run after PostgreSQL COMMIT on a NEW registry cursor.

    Never reuse request.env / the request cursor here: that cursor is
    closed or still the pre-commit snapshot. Redis is updated only after
    the mutation is durable in PostgreSQL.
    """
    def _callback():
        try:
            import odoo
            from odoo import api, SUPERUSER_ID
            from odoo.addons.auction_module.services import auction_live_snapshot_service as snap
            registry = odoo.registry(dbname)
            cr = registry.cursor()
            try:
                env = api.Environment(
                    cr, SUPERUSER_ID,
                    {'auction_skip_tournament_security': True},
                )
                for tid, kinds in dirty.items():
                    seq = seqs.get(int(tid))
                    snap.rebuild_tournament_snapshots(
                        env, int(tid), seq, kinds,
                    )
            except Exception:
                _logger.warning(
                    'auction live snapshot postcommit failed db=%s',
                    dbname, exc_info=True,
                )
            finally:
                try:
                    cr.close()
                except Exception:
                    pass
        except Exception:
            _logger.warning(
                'auction live snapshot postcommit setup failed db=%s',
                dbname, exc_info=True,
            )
    return _callback


def mark_tournament_dirty(env, tournament_ids, kinds):
    """Register dirty snapshot kinds for one or more tournaments on this cursor.

    Safe to call from raw-SQL paths (e.g. set_dice_state) that bypass ORM write.
    Never raises into business logic.
    """
    if env.context.get('auction_skip_live_snapshot'):
        return
    if not kinds or not tournament_ids:
        return
    try:
        cr = env.cr
        dirty = _cursor_state(cr)
        kinds = frozenset(kinds)
        for tid in tournament_ids:
            if not tid:
                continue
            tid = int(tid)
            bucket = dirty.get(tid)
            if bucket is None:
                dirty[tid] = set(kinds)
                _bump_seq(cr, tid)
                try:
                    env['auction.tournament'].invalidate_cache(
                        ['live_snapshot_seq'], [tid],
                    )
                except Exception:
                    pass
            else:
                bucket.update(kinds)
        if not cr._auction_live_postcommit and dirty:
            # One callback per transaction; the dict is mutated until COMMIT.
            cr.postcommit.add(_postcommit_rebuild(
                cr.dbname, dirty, cr._auction_live_seqs,
            ))
            cr._auction_live_postcommit = True
    except Exception:
        _logger.warning('auction live snapshot mark_dirty failed', exc_info=True)


class AuctionLiveSnapshotMixin(models.AbstractModel):
    _name = 'auction.live.snapshot.mixin'
    _description = 'Live snapshot mutation watcher'

    def _ac_live_tournament_ids(self):
        ids = set()
        name = self._name
        if name == 'auction.tournament':
            ids.update(self.ids)
            return ids
        if 'tournament_id' in self._fields:
            for rec in self:
                tid = rec.tournament_id.id if rec.tournament_id else False
                if tid:
                    ids.add(tid)
        if name in ('auction.auction.player',) and 'auction_id' in self._fields:
            for rec in self:
                auc = rec.auction_id
                if auc and auc.tournament_id:
                    ids.add(auc.tournament_id.id)
        if name in ('auction.auction.tier.limit', 'auction.auction.bid.slab') and 'auction_id' in self._fields:
            for rec in self:
                auc = rec.auction_id
                if auc and auc.tournament_id:
                    ids.add(auc.tournament_id.id)
        return ids

    def _ac_live_touch(self, vals, create=False, unlink=False):
        kinds = kinds_for_vals(self._name, vals, create=create, unlink=unlink)
        if not kinds:
            return
        mark_tournament_dirty(self.env, self._ac_live_tournament_ids(), kinds)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        try:
            if self._name in WATCHED_FIELDS or self._name in WATCH_CREATE_UNLINK:
                for rec, vals in zip(records, vals_list):
                    rec._ac_live_touch(vals, create=True)
        except Exception:
            _logger.warning('auction live snapshot create hook failed', exc_info=True)
        return records

    def write(self, vals):
        res = super().write(vals)
        try:
            if self._name in WATCHED_FIELDS:
                self._ac_live_touch(vals, create=False)
        except Exception:
            _logger.warning('auction live snapshot write hook failed', exc_info=True)
        return res

    def unlink(self):
        try:
            if self._name in WATCHED_FIELDS or self._name in WATCH_CREATE_UNLINK:
                tids = self._ac_live_tournament_ids()
                kinds = kinds_for_vals(self._name, None, unlink=True)
                if not kinds:
                    kinds = kinds_for_vals(self._name, {f: True for f in (WATCHED_FIELDS.get(self._name) or {})}, unlink=True)
                mark_tournament_dirty(self.env, tids, kinds)
        except Exception:
            _logger.warning('auction live snapshot unlink hook failed', exc_info=True)
        return super().unlink()
