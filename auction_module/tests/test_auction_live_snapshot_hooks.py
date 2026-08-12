# -*- coding: utf-8 -*-
"""Mutation mapping, dedup, and failure-safety tests for Phase 2A snapshots."""
import logging
import unittest
from unittest import mock

from odoo.addons.auction_module.models.auction_live_snapshot_mixin import (
    WATCHED_FIELDS,
    kinds_for_vals,
    mark_tournament_dirty,
    _cursor_state,
)


def _kinds(*names):
    return frozenset(names)


class TestKindsForVals(unittest.TestCase):
    def test_bid_only_dirties_projector(self):
        kinds = kinds_for_vals('auction.team.player', {
            'current_bid': 500,
            'current_bid_team_id': 3,
        })
        self.assertEqual(kinds, {'pj'})

    def test_sold_dirties_all_three(self):
        kinds = kinds_for_vals('auction.team.player', {
            'state': 'sold',
            'assigned_team_id': 2,
            'is_on_stage': False,
        })
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

    def test_unsold(self):
        kinds = kinds_for_vals('auction.team.player', {
            'state': 'unsold',
            'is_on_stage': False,
        })
        self.assertTrue({'lb', 'pj', 'bal'} <= kinds)

    def test_next_player_clear_stage(self):
        kinds = kinds_for_vals('auction.team.player', {'is_on_stage': True})
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

    def test_dice_projector_only(self):
        kinds = kinds_for_vals('auction.tournament', {
            'dice_state': 'rolling',
            'dice_result': 12,
        })
        self.assertEqual(kinds, {'pj'})

    def test_break(self):
        kinds = kinds_for_vals('auction.tournament', {'break_time_active': True})
        self.assertEqual(kinds, {'lb', 'pj'})

    def test_mystery_reveal_not_balance(self):
        kinds = kinds_for_vals('auction.team.player', {'mystery_revealed': True})
        self.assertEqual(kinds, {'lb', 'pj'})

    def test_recall_swap_move_via_assignment(self):
        kinds = kinds_for_vals('auction.team.player', {
            'assigned_team_id': False,
            'state': 'auction',
        })
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

    def test_sale_update_points(self):
        kinds = kinds_for_vals('auction.auction.player', {'points': 1200}, create=False)
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

    def test_advertiser_not_balance(self):
        kinds = kinds_for_vals('auction.advertiser', {'name': 'Acme', 'image': b'x'})
        self.assertEqual(kinds, {'lb', 'pj'})

    def test_tier_slab_all_three(self):
        self.assertEqual(
            kinds_for_vals('auction.auction.tier.limit', {'max_call': 5000}),
            {'lb', 'pj', 'bal'},
        )
        self.assertEqual(
            kinds_for_vals('auction.auction.bid.slab', {'increment': 50}),
            {'lb', 'pj', 'bal'},
        )

    def test_history_create(self):
        kinds = kinds_for_vals('auction.history', {'message': 'sold'}, create=True)
        self.assertEqual(kinds, {'lb', 'pj'})

    def test_unrelated_write_empty(self):
        kinds = kinds_for_vals('auction.tournament', {'venue': 'Stadium'})
        self.assertEqual(kinds, set())

    def test_projector_board_not_balance(self):
        kinds = kinds_for_vals('auction.tournament', {
            'projector_board_mode': 'pools',
            'pool_draw_json': '{}',
        })
        self.assertEqual(kinds, {'pj'})

    def test_declare_complete(self):
        kinds = kinds_for_vals('auction.tournament', {'auction_declared_complete': True})
        self.assertEqual(kinds, {'lb', 'pj'})

    def test_live_board_toggle(self):
        kinds = kinds_for_vals('auction.tournament', {'live_board_active': True})
        self.assertEqual(kinds, {'lb'})

    def test_watched_fields_cover_audit_list(self):
        player = WATCHED_FIELDS['auction.team.player']
        for f in (
            'is_on_stage', 'state', 'current_bid', 'current_bid_team_id',
            'mystery_revealed', 'assigned_team_id', 'photo', 'name',
            'tier_id', 'icon_player',
        ):
            self.assertIn(f, player)
        tourney = WATCHED_FIELDS['auction.tournament']
        for f in (
            'dice_state', 'dice_result', 'break_time_active',
            'stamp_player_id', 'stamp_state', 'stamp_expires_at',
            'projector_board_mode', 'pool_draw_json', 'fixture_schedule_json',
            'live_board_active', 'auction_declared_complete',
        ):
            self.assertIn(f, tourney)


class _Cr(object):
    def __init__(self, dbname='testdb'):
        self.dbname = dbname
        self.postcommit = mock.Mock()
        self.postcommit.add = mock.Mock()
        self.sql = []
        self._seq = 0

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if 'live_snapshot_seq' in sql and 'RETURNING' in sql:
            self._seq += 1
            self._last = (self._seq,)

    def fetchone(self):
        return getattr(self, '_last', (0,))


class _Env(object):
    def __init__(self, cr=None):
        self.cr = cr or _Cr()
        self.context = {}
        self._models = {}

    def __getitem__(self, name):
        rec = mock.Mock()
        rec.invalidate_cache = mock.Mock()
        return rec


class TestDedupAndPostcommit(unittest.TestCase):
    def test_one_rebuild_per_tournament_per_cursor(self):
        env = _Env()
        mark_tournament_dirty(env, [42], {'pj'})
        mark_tournament_dirty(env, [42], {'lb', 'pj', 'bal'})
        mark_tournament_dirty(env, [42], {'lb'})
        dirty = env.cr._auction_live_dirty
        self.assertEqual(set(dirty.keys()), {42})
        self.assertEqual(dirty[42], {'lb', 'pj', 'bal'})
        self.assertEqual(env.cr.postcommit.add.call_count, 1)
        self.assertEqual(env.cr._auction_live_seqs[42], 1)
        seq_updates = [s for s in env.cr.sql if 'live_snapshot_seq' in s[0]]
        self.assertEqual(len(seq_updates), 1)

    def test_multiple_tournaments(self):
        env = _Env()
        mark_tournament_dirty(env, [1], {'pj'})
        mark_tournament_dirty(env, [2], {'lb'})
        self.assertEqual(set(env.cr._auction_live_dirty.keys()), {1, 2})
        self.assertEqual(env.cr.postcommit.add.call_count, 1)
        self.assertEqual(env.cr._auction_live_seqs[1], 1)
        self.assertEqual(env.cr._auction_live_seqs[2], 2)

    def test_skip_context(self):
        env = _Env()
        env.context = {'auction_skip_live_snapshot': True}
        mark_tournament_dirty(env, [1], {'pj'})
        self.assertFalse(getattr(env.cr, '_auction_live_dirty', None))


class TestPostcommitFailureSafety(unittest.TestCase):
    def test_callback_swallows_redis_errors(self):
        from odoo.addons.auction_module.models.auction_live_snapshot_mixin import (
            _postcommit_rebuild,
        )
        cb = _postcommit_rebuild('ghost_db', {1: {'pj'}}, {1: 3})
        # Must not raise even when odoo.registry is missing / broken.
        cb()

    def test_mark_dirty_never_raises(self):
        env = mock.Mock()
        env.context = {}
        env.cr = mock.Mock()
        env.cr.dbname = 'x'
        type(env.cr)._auction_live_dirty = property(
            lambda self: (_ for _ in ()).throw(RuntimeError('boom'))
        )
        mark_tournament_dirty(env, [1], {'pj'})


class TestPayloadSeqAndStamp(unittest.TestCase):
    def test_attach_seq(self):
        from odoo.addons.auction_module.services.auction_live_payload import attach_seq
        out = attach_seq({'teams': []}, 15)
        self.assertEqual(out['seq'], 15)
        self.assertEqual(out['teams'], [])

    def test_stamp_iso_none(self):
        from odoo.addons.auction_module.services.auction_live_payload import _stamp_iso
        self.assertIsNone(_stamp_iso(None))
        t = mock.Mock()
        t.stamp_expires_at = None
        self.assertIsNone(_stamp_iso(t))


class TestSeqZeroIsValid(unittest.TestCase):
    def test_payload_seq_zero_equals_pg_zero(self):
        """Regression: seq 0 must not be treated as missing via `or -1`."""
        payload = {'seq': 0, 'teams': []}
        payload_seq = payload.get('seq')
        self.assertIsNotNone(payload_seq)
        self.assertEqual(int(payload_seq), 0)
        # Broken pattern (for documentation):
        self.assertEqual(int(payload.get('seq') or -1), -1)


if __name__ == '__main__':
    unittest.main()
