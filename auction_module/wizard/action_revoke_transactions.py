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

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AuctionRevokeTransactionsWizard(models.TransientModel):
    _name = 'auction.revoke.transactions.wizard'
    _description = 'Restore Tournament Transactions'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    tournament_name = fields.Char(related='tournament_id.name', readonly=True)

    clear_stage = fields.Boolean(
        string='Clear Stage?',
        default=True,
        help='Reset players currently on stage and clear the live-board stamp. '
             'The projector / live display returns to waiting.',
    )
    clear_history = fields.Boolean(
        string='Clear History',
        default=True,
        help='Permanently delete this tournament’s auction history records. '
             'Those entries cannot be recovered.',
    )
    revoke_sold = fields.Boolean(
        string='Restore Sold Players?',
        default=True,
        help='Recall all sold players back to In Auction. Team assignments and '
             'sale amounts for those players are reversed.',
    )
    revoke_unsold = fields.Boolean(
        string='Restore Unsold Players',
        default=True,
        help='Bring all unsold players back to In Auction so they can be called again.',
    )
    accept_warning = fields.Boolean(
        string='I understand this cannot be undone',
        default=False,
        help='You must accept that restored states cannot be returned to the original '
             'sold, unsold, or history records from this screen.',
    )

    stage_count = fields.Integer(compute='_compute_counts')
    history_count = fields.Integer(compute='_compute_counts')
    sold_count = fields.Integer(compute='_compute_counts')
    unsold_count = fields.Integer(compute='_compute_counts')

    @api.depends('tournament_id')
    def _compute_counts(self):
        Player = self.env['auction.team.player'].sudo()
        History = self.env['auction.history'].sudo().with_context(active_test=False)
        for wiz in self:
            tid = wiz.tournament_id.id
            if not tid:
                wiz.stage_count = wiz.history_count = wiz.sold_count = wiz.unsold_count = 0
                continue
            wiz.stage_count = Player.search_count([
                ('tournament_id', '=', tid), ('is_on_stage', '=', True),
            ])
            wiz.history_count = History.search_count([('tournament_id', '=', tid)])
            wiz.sold_count = Player.search_count([
                ('tournament_id', '=', tid), ('state', '=', 'sold'),
            ])
            wiz.unsold_count = Player.search_count([
                ('tournament_id', '=', tid), ('state', '=', 'unsold'),
            ])

    def _players(self, state):
        self.ensure_one()
        return self.env['auction.team.player'].sudo().search([
            ('tournament_id', '=', self.tournament_id.id),
            ('state', '=', state),
        ])

    def action_apply(self):
        self.ensure_one()
        if not self.accept_warning:
            raise UserError(_(
                'Please read the warning and tick “I understand and accept” before restoring.'
            ))
        if not any((self.clear_stage, self.clear_history, self.revoke_sold, self.revoke_unsold)):
            raise UserError(_('Select at least one action to restore.'))

        tournament = self.tournament_id
        parts = []

        if self.revoke_sold:
            sold = self._players('sold')
            if sold:
                sold.with_context(mass_update=True).action_recall_auction_sold()
            parts.append(_('%s sold player(s) recalled') % len(sold))

        if self.revoke_unsold:
            unsold = self._players('unsold')
            if unsold:
                unsold.with_context(mass_update=True).action_auction()
            parts.append(_('%s unsold player(s) reopened') % len(unsold))

        if self.clear_stage:
            tournament.action_clear_stage()
            tournament.sudo().write({
                'stamp_player_id': False,
                'stamp_state': False,
                'stamp_expires_at': False,
            })
            parts.append(_('%s on-stage player(s) cleared') % self.stage_count)

        if self.clear_history:
            tournament.with_context(revoke_wizard=True).action_clear_auction_history()
            parts.append(_('%s history record(s) deleted') % self.history_count)

        message = _('Restore complete: %s.') % ', '.join(parts)
        if hasattr(self.env.user, 'notify_success'):
            self.env.user.notify_success(message)
        return {'type': 'ir.actions.act_window_close'}
