# -*- coding: utf-8 -*-
"""Odoo TransactionCase tests — run with odoo-bin --test-enable -u auction_module."""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'auction_live_snapshot')
class TestLiveSnapshotOdoo(TransactionCase):
    def _make_tournament(self):
        return self.env['auction.tournament'].create({
            'name': 'Phase2A Seq Test',
            'description': 'snapshot seq',
            'tournament_type': 'cricket',
        })

    def test_live_snapshot_seq_default(self):
        t = self._make_tournament()
        self.assertEqual(t.live_snapshot_seq, 0)

    def test_seq_bumps_once_for_multi_model_write(self):
        t = self._make_tournament()
        player = self.env['auction.team.player'].create({
            'name': 'Snap Player',
            'tournament_id': t.id,
            'state': 'auction',
        })
        t.invalidate_cache(['live_snapshot_seq'])
        after_create = t.live_snapshot_seq
        self.assertEqual(after_create, 1)
        # Same transaction: sell-like writes must not bump again.
        player.write({
            'state': 'sold',
            'is_on_stage': False,
        })
        self.env['auction.history'].create({
            'tournament_id': t.id,
            'player_id': player.id,
            'message': 'Snap Player sold',
        })
        t.write({
            'stamp_state': 'sold',
            'stamp_player_id': player.id,
        })
        t.invalidate_cache(['live_snapshot_seq'])
        self.assertEqual(t.live_snapshot_seq, after_create)
        dirty = getattr(self.env.cr, '_auction_live_dirty', {})
        self.assertIn(t.id, dirty)
        self.assertTrue({'lb', 'pj'} <= dirty[t.id])

    def test_bid_does_not_mark_balance(self):
        t = self._make_tournament()
        player = self.env['auction.team.player'].create({
            'name': 'Bid Player',
            'tournament_id': t.id,
            'state': 'auction',
            'is_on_stage': True,
        })
        # current_bid may be added by auction_auctioneer
        if 'current_bid' not in player._fields:
            self.skipTest('auction_auctioneer not installed')
        # reset dirty from create
        if hasattr(self.env.cr, '_auction_live_dirty'):
            self.env.cr._auction_live_dirty.clear()
            self.env.cr._auction_live_seqs.clear()
            self.env.cr._auction_live_postcommit = False
        player.write({'current_bid': 250})
        dirty = self.env.cr._auction_live_dirty.get(t.id, set())
        self.assertEqual(dirty, {'pj'})

    def test_unrelated_tournament_write_skips(self):
        t = self._make_tournament()
        if hasattr(self.env.cr, '_auction_live_dirty'):
            self.env.cr._auction_live_dirty.clear()
            self.env.cr._auction_live_seqs.clear()
        t.write({'venue': 'No snapshot please'})
        dirty = getattr(self.env.cr, '_auction_live_dirty', {}) or {}
        self.assertNotIn(t.id, dirty)

    def test_dice_raw_sql_marks_projector(self):
        t = self._make_tournament()
        if hasattr(self.env.cr, '_auction_live_dirty'):
            self.env.cr._auction_live_dirty.clear()
            self.env.cr._auction_live_seqs.clear()
            self.env.cr._auction_live_postcommit = False
        t.set_dice_state('rolling', 7)
        dirty = getattr(self.env.cr, '_auction_live_dirty', {}) or {}
        self.assertEqual(dirty.get(t.id), {'pj'})
