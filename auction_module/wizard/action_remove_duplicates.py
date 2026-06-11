# -*- coding: utf-8 -*-
import hashlib

from odoo import api, fields, models
from odoo.exceptions import UserError


class AuctionRemoveDuplicateLine(models.TransientModel):
    _name = 'auction.remove.duplicate.line'
    _description = 'Duplicate Player Line'

    wizard_id = fields.Many2one('auction.remove.duplicates.wizard', ondelete='cascade')
    player_id = fields.Many2one('auction.team.player', string='Duplicate (Remove)', readonly=True)
    keep_player_id = fields.Many2one('auction.team.player', string='Original (Keep)', readonly=True)
    player_sl_no = fields.Integer(related='player_id.sl_no', string='Sl No', store=False)
    player_name = fields.Char(related='player_id.name', string='Name', store=False)
    player_contact = fields.Char(related='player_id.contact', string='Mobile', store=False)
    player_state = fields.Selection(related='player_id.state', string='State', store=False)
    match_reason = fields.Char(string='Reason', readonly=True)
    should_remove = fields.Boolean(string='Remove?', default=True)


class AuctionRemoveDuplicatesWizard(models.TransientModel):
    _name = 'auction.remove.duplicates.wizard'
    _description = 'Remove Duplicate Players Wizard'

    tournament_id = fields.Many2one('auction.tournament', string='Tournament', required=True)

    # ── Match criteria ────────────────────────────────────────────────────
    match_by_name = fields.Boolean('Same Name', default=True)
    match_by_contact = fields.Boolean('Same Mobile Number', default=True)
    match_by_photo = fields.Boolean('Same Photo', default=False)

    # ── Player states to include ──────────────────────────────────────────
    include_draft = fields.Boolean('Draft Players', default=True)
    include_auction = fields.Boolean('In Auction Players', default=True)

    # ── Wizard step ───────────────────────────────────────────────────────
    step = fields.Selection(
        [('configure', 'Configure'), ('preview', 'Preview')],
        default='configure',
    )

    line_ids = fields.One2many('auction.remove.duplicate.line', 'wizard_id', string='Duplicates Found')
    duplicate_count = fields.Integer(compute='_compute_counts', store=False)
    selected_count = fields.Integer(compute='_compute_counts', store=False)

    @api.depends('line_ids', 'line_ids.should_remove')
    def _compute_counts(self):
        for rec in self:
            rec.duplicate_count = len(rec.line_ids)
            rec.selected_count = len(rec.line_ids.filtered('should_remove'))

    # ── Step 1 → Step 2: scan for duplicates ─────────────────────────────
    def action_find_duplicates(self):
        if not any([self.match_by_name, self.match_by_contact, self.match_by_photo]):
            raise UserError('Please select at least one match criterion (Name, Mobile, or Photo).')
        if not any([self.include_draft, self.include_auction]):
            raise UserError('Please include at least one player state (Draft or In Auction).')

        states = []
        if self.include_draft:
            states.append('draft')
        if self.include_auction:
            states.append('auction')

        players = self.env['auction.team.player'].search(
            [('tournament_id', '=', self.tournament_id.id), ('state', 'in', states)],
            order='sl_no asc, id asc',
        )

        # Track first-seen canonical record for each key
        seen_name = {}     # normalised name  → player
        seen_contact = {}  # stripped contact → player
        seen_photo = {}    # md5 hex          → player

        # player_id → {keep_player, set_of_reasons}
        to_remove = {}

        for player in players:
            reasons = set()
            keep = None

            if self.match_by_name and player.name:
                key = player.name.strip().lower()
                if key in seen_name:
                    reasons.add('Same Name')
                    keep = seen_name[key]
                else:
                    seen_name[key] = player

            if self.match_by_contact and player.contact and player.contact.strip():
                key = player.contact.strip()
                if key in seen_contact:
                    reasons.add('Same Mobile')
                    if not keep:
                        keep = seen_contact[key]
                else:
                    seen_contact[key] = player

            if self.match_by_photo and player.photo:
                h = hashlib.md5(player.photo).hexdigest()
                if h in seen_photo:
                    reasons.add('Same Photo')
                    if not keep:
                        keep = seen_photo[h]
                else:
                    seen_photo[h] = player

            if reasons and keep and player.id != keep.id:
                if player.id not in to_remove:
                    to_remove[player.id] = {'keep': keep, 'reasons': reasons}
                else:
                    to_remove[player.id]['reasons'].update(reasons)

        # Rebuild lines
        self.line_ids.unlink()
        lines = [
            (0, 0, {
                'player_id': pid,
                'keep_player_id': info['keep'].id,
                'match_reason': ', '.join(sorted(info['reasons'])),
                'should_remove': True,
            })
            for pid, info in to_remove.items()
        ]
        self.write({'line_ids': lines, 'step': 'preview'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Standalone resequence (no duplicate detection needed) ────────────
    def action_resequence_only(self):
        if not any([self.include_draft, self.include_auction]):
            raise UserError('Please include at least one player state (Draft or In Auction) to resequence.')

        states = []
        if self.include_draft:
            states.append('draft')
        if self.include_auction:
            states.append('auction')

        players = self.env['auction.team.player'].search(
            [('tournament_id', '=', self.tournament_id.id), ('state', 'in', states)],
            order='sl_no asc, id asc',
        )
        if not players:
            raise UserError('No players found in the selected states for this tournament.')

        updated = 0
        for i, player in enumerate(players, start=1):
            if player.sl_no != i:
                player.sl_no = i
                updated += 1

        self.env.user.notify_success(
            message='%d player(s) resequenced (1 – %d). %d sequence number(s) updated.' % (
                len(players), len(players), updated),
            title='Resequence Complete ✓',
        )
        return {'type': 'ir.actions.act_window_close'}

    # ── Reset base price + live bid for all In-Auction players ───────────
    def action_reset_auction_bids(self):
        players = self.env['auction.team.player'].search([
            ('tournament_id', '=', self.tournament_id.id),
            ('state', '=', 'auction'),
        ])
        if not players:
            raise UserError('No players are currently In Auction for this tournament.')

        players.write({
            'base_price': 0,
            'current_bid': 0,
            'current_bid_team_id': False,
        })

        self.env.user.notify_success(
            message='%d In-Auction player(s) reset: base price, live bid price and live bid team cleared.' % len(players),
            title='Auction Bids Reset ✓',
        )
        return {'type': 'ir.actions.act_window_close'}

    # ── Step 2 → Step 1: back ─────────────────────────────────────────────
    def action_back(self):
        self.write({'step': 'configure', 'line_ids': [(5, 0, 0)]})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Step 2: execute removal + resequence ─────────────────────────────
    def action_remove_and_resequence(self):
        lines_to_remove = self.line_ids.filtered('should_remove')
        if not lines_to_remove:
            raise UserError('No duplicates are selected for removal. Check the "Remove?" column.')

        players_to_delete = lines_to_remove.mapped('player_id')
        count = len(players_to_delete)
        players_to_delete.unlink()

        # Resequence remaining players in this tournament (all states, ordered by current sl_no)
        remaining = self.env['auction.team.player'].search(
            [('tournament_id', '=', self.tournament_id.id)],
            order='sl_no asc, id asc',
        )
        for i, player in enumerate(remaining, start=1):
            if player.sl_no != i:
                player.sl_no = i

        self.env.user.notify_success(
            message='%d duplicate(s) removed. Sequence numbers reissued 1 – %d.' % (count, len(remaining)),
            title='Duplicates Removed ✓',
        )
        return {'type': 'ir.actions.act_window_close'}
