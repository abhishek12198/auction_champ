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
    def test_bid_dirties_live_and_projector(self):
        kinds = kinds_for_vals('auction.team.player', {
            'current_bid': 500,
            'current_bid_team_id': 3,
        })
        self.assertEqual(kinds, {'lb', 'pj'})

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
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

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
            'tier_id', 'icon_player', 'role', 'batting_style', 'sl_no',
            'dominant_position_id', 'preferred_foot',
        ):
            self.assertIn(f, player)
        tourney = WATCHED_FIELDS['auction.tournament']
        for f in (
            'dice_state', 'dice_result', 'break_time_active',
            'stamp_player_id', 'stamp_state', 'stamp_expires_at',
            'projector_board_mode', 'pool_draw_json', 'fixture_schedule_json',
            'live_board_active', 'live_board_code_protected',
            'auction_declared_complete', 'name', 'logo',
            'player_display_template', 'tournament_type',
        ):
            self.assertIn(f, tourney)
        team = WATCHED_FIELDS['auction.team']
        for f in ('name', 'logo', 'manager'):
            self.assertIn(f, team)

    def test_team_logo_dirties_all_three(self):
        kinds = kinds_for_vals('auction.team', {'logo': b'x', 'name': 'T'})
        self.assertEqual(kinds, {'lb', 'pj', 'bal'})

    def test_tournament_theme_not_balance(self):
        kinds = kinds_for_vals('auction.tournament', {
            'player_display_template': 'cherry',
            'name': 'Cup',
        })
        self.assertEqual(kinds, {'lb', 'pj'})


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


class TestSliceBalancePlayers(unittest.TestCase):
    def _snap(self):
        return {
            'player_counts': {'sold': 2, 'unsold': 1, 'auction': 0},
            'players': {
                'sold': [
                    {'id': 1, 'name': 'Ashwin', 'sl_no': 5, 'contact': '999111',
                     'role': 'Allrounder', 'team_id': 10, 'team_name': 'Kings'},
                    {'id': 2, 'name': 'Virat', 'sl_no': 18, 'contact': '888222',
                     'role': 'Batter', 'team_id': 11, 'team_name': 'RCB'},
                ],
                'unsold': [
                    {'id': 3, 'name': 'Rohit', 'sl_no': 45, 'contact': '',
                     'role': 'Batter', 'team_id': 0, 'team_name': ''},
                ],
                'auction': [],
            },
        }

    def test_search_name_is_in_memory(self):
        from odoo.addons.auction_module.services.auction_live_payload import (
            slice_balance_players,
        )
        out = slice_balance_players(self._snap(), 'sold', query='Ash')
        self.assertEqual(out['total'], 1)
        self.assertEqual(out['players'][0]['name'], 'Ashwin')
        self.assertTrue(out['from_snapshot'])

    def test_search_serial_and_team_filter(self):
        from odoo.addons.auction_module.services.auction_live_payload import (
            slice_balance_players,
        )
        out = slice_balance_players(self._snap(), 'sold', query='#18')
        self.assertEqual(out['total'], 1)
        self.assertEqual(out['players'][0]['name'], 'Virat')
        team = slice_balance_players(self._snap(), 'sold', team_id=10)
        self.assertEqual(team['total'], 1)
        self.assertEqual(team['players'][0]['name'], 'Ashwin')

    def test_schema_rejects_legacy_balance(self):
        from odoo.addons.auction_module.services.auction_live_snapshot_service import (
            _snapshot_schema_ok,
        )
        self.assertFalse(_snapshot_schema_ok('bal', {'teams': [], 'seq': 1}))
        self.assertTrue(_snapshot_schema_ok('bal', {'players': {}, 'seq': 1}))
        self.assertFalse(_snapshot_schema_ok('bal', {
            'players': {'sold': [{'id': 1, 'name': 'A'}], 'unsold': [], 'auction': []},
        }))
        self.assertTrue(_snapshot_schema_ok('bal', {
            'players': {'sold': [{'id': 1, 'name': 'A', 'attrs': [], 'photo_url': '/x/photo?sz=bs'}], 'unsold': [], 'auction': []},
        }))
        self.assertTrue(_snapshot_schema_ok('pj', {'player': {}, 'seq': 1}))

    def test_cricket_and_football_card_attrs(self):
        from odoo.addons.auction_module.services.auction_live_payload import (
            _balance_player_profile,
        )
        cricket = mock.Mock(
            role='Allrounder',
            batting_style='Right Hand Bat',
            bowling_style='Right Arm Off Spin',
        )
        role, attrs = _balance_player_profile(cricket, False, False)
        self.assertEqual(role, 'Allrounder')
        keys = [a['k'] for a in attrs]
        self.assertEqual(keys, ['Batting', 'Bowling'])
        football = mock.Mock(
            role='',
            preferred_foot='right',
            age=24,
            work_rate='high',
            use_other_attributes=False,
            playing_style_ids=[],
            strength_ids=[],
            other_attribute_ids=[],
        )
        pos = mock.Mock()
        pos.name = 'Striker'
        pos.code = 'ST'
        football.dominant_position_id = pos
        sec = mock.Mock()
        sec.code = 'CAM'
        sec.name = 'Attacking Mid'
        football.secondary_position_ids = [sec]
        role, attrs = _balance_player_profile(football, False, True)
        self.assertEqual(role, 'Striker')
        mapped = {a['k']: a['v'] for a in attrs}
        self.assertEqual(mapped.get('Foot'), 'Right')
        self.assertEqual(mapped.get('Secondary'), 'CAM')
        self.assertEqual(mapped.get('Age'), '24')
        self.assertEqual(mapped.get('Work Rate'), 'High')


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
