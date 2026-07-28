# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import hashlib
import re

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


class AuctionRemoveSerialLine(models.TransientModel):
    _name = 'auction.remove.serial.line'
    _description = 'Serial Remove Player Line'
    _order = 'player_sl_no, id'

    wizard_id = fields.Many2one('auction.remove.duplicates.wizard', ondelete='cascade')
    player_id = fields.Many2one(
        'auction.team.player', string='Player', readonly=True, required=False,
    )
    player_sl_no = fields.Integer(related='player_id.sl_no', string='Sl No', store=False)
    player_photo = fields.Binary(related='player_id.photo', string='Photo', store=False)
    player_name = fields.Char(compute='_compute_player_display', string='Name')
    player_contact = fields.Char(related='player_id.contact', string='Mobile', store=False)
    player_role = fields.Char(related='player_id.role', string='Role', store=False)
    player_position = fields.Char(compute='_compute_player_display', string='Position')
    tournament_type = fields.Selection(
        related='player_id.tournament_type', string='Sport', store=False,
    )

    @api.depends(
        'player_id', 'player_id.name',
        'player_id.dominant_position_id', 'player_id.dominant_position_id.name',
    )
    def _compute_player_display(self):
        for line in self:
            line.player_name = (line.player_id.name or '').upper()
            pos = line.player_id.dominant_position_id
            line.player_position = (pos.name or pos.code or '') if pos else ''


class AuctionRemoveDuplicatesWizard(models.TransientModel):
    _name = 'auction.remove.duplicates.wizard'
    _description = 'Remove Duplicate Players Wizard'

    tournament_id = fields.Many2one('auction.tournament', string='Tournament', required=True)
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', string='Sport', readonly=True,
    )

    # ── Match criteria ────────────────────────────────────────────────────
    match_by_name = fields.Boolean('Same Name', default=True)
    match_by_contact = fields.Boolean('Same Mobile Number', default=True)
    match_by_photo = fields.Boolean('Same Photo', default=False)

    # ── Player states to include ──────────────────────────────────────────
    include_draft = fields.Boolean('Draft Players', default=True)
    include_auction = fields.Boolean('In Auction Players', default=True)

    # ── Remove by serial (draft only) ─────────────────────────────────────
    delete_by_serial = fields.Boolean(
        string='Delete by Serial Number?',
        default=False,
        help='When enabled, enter draft player serial numbers to delete and resequence.',
    )
    serial_nos = fields.Text(
        string='Serial Numbers',
        help='Comma-separated player serial numbers (sl_no). Only draft players are matched.',
    )
    serial_line_ids = fields.One2many(
        'auction.remove.serial.line', 'wizard_id', string='Matched Draft Players',
    )
    serial_match_count = fields.Integer(compute='_compute_serial_counts', store=False)
    serial_info = fields.Char(string='Serial Info', readonly=True)

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

    @api.depends('serial_line_ids')
    def _compute_serial_counts(self):
        for rec in self:
            rec.serial_match_count = len(rec.serial_line_ids)

    def _parse_serial_nos(self):
        """Parse comma/space/semicolon separated serial numbers into unique ints."""
        self.ensure_one()
        raw = self.serial_nos or ''
        parts = re.split(r'[,;\s]+', raw.strip())
        nos = []
        seen = set()
        for part in parts:
            if not part:
                continue
            try:
                num = int(float(part))
            except (TypeError, ValueError):
                continue
            if num not in seen:
                seen.add(num)
                nos.append(num)
        return nos

    def _find_draft_players_by_serial(self):
        """Return draft players matching entered serials, plus missing serial list."""
        self.ensure_one()
        nos = self._parse_serial_nos()
        if not nos or not self.tournament_id:
            return self.env['auction.team.player'], [], nos

        players = self.env['auction.team.player'].search(
            [
                ('tournament_id', '=', self.tournament_id.id),
                ('state', '=', 'draft'),
                ('sl_no', 'in', nos),
            ],
            order='sl_no asc, id asc',
        )
        found = set(players.mapped('sl_no'))
        missing = [n for n in nos if n not in found]
        return players, missing, nos

    @api.onchange('serial_nos', 'tournament_id')
    def _onchange_serial_nos(self):
        players, missing, nos = self._find_draft_players_by_serial()
        commands = [(5, 0, 0)]
        for player in players:
            commands.append((0, 0, {'player_id': player.id}))
        self.serial_line_ids = commands

        if not nos:
            self.serial_info = False
        elif missing:
            self.serial_info = (
                'No draft player for serial(s): %s '
                '(only Draft players are listed; other states are ignored).'
            ) % ', '.join(str(n) for n in missing)
        else:
            self.serial_info = '%d draft player(s) matched.' % len(players)

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

        seen_name = {}
        seen_contact = {}
        seen_photo = {}
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

    # ── Remove by serial numbers (draft only) + resequence all remaining ─
    def action_remove_by_serial(self):
        self.ensure_one()
        # Always resolve from serial_nos (source of truth). Do not rely on
        # transient o2m lines, which the web client may recreate without player_id.
        players, _missing, nos = self._find_draft_players_by_serial()
        if not nos:
            raise UserError('Enter at least one serial number.')

        players = players.filtered(
            lambda p: p.exists() and p.state == 'draft' and p.tournament_id == self.tournament_id
        )

        if not players:
            raise UserError(
                'No draft players matched the given serial numbers. '
                'Only players in Draft state can be removed this way.'
            )

        # Safety: never delete non-draft
        non_draft = players.filtered(lambda p: p.state != 'draft')
        if non_draft:
            raise UserError(
                'Cannot remove players that are not in Draft state: %s' % (
                    ', '.join('%s (#%s)' % (p.name, p.sl_no) for p in non_draft)
                )
            )

        count = len(players)
        players.unlink()

        remaining = self.env['auction.team.player'].search(
            [('tournament_id', '=', self.tournament_id.id)],
            order='sl_no asc, id asc',
        )
        for i, player in enumerate(remaining, start=1):
            if player.sl_no != i:
                player.sl_no = i

        self.env.user.notify_success(
            message='%d draft player(s) removed. Sequence numbers reissued 1 – %d.' % (
                count, len(remaining)),
            title='Players Removed ✓',
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
