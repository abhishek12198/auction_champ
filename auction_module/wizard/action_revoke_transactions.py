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
        help='Permanently delete this tournament’s auction history records and reset '
             'any live bids on players (current bid / leading team) back to default. '
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
        help='Bring all unsold players back so they can be called again.',
    )
    restore_to = fields.Selection(
        [
            ('auction', 'In Auction'),
            ('draft', 'Draft'),
        ],
        string='Where should restored players go?',
        default='auction',
        required=True,
        help='Pick one destination for sold and unsold players you ticked above.',
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

    def _clear_tournament_live_bids(self, tournament):
        """Reset live bids on this tournament's players to default (0 / no team).

        Returns how many players had a non-default bid cleared. Never raises —
        bid reset must not roll back sold/unsold/history restore.
        """
        self.ensure_one()
        Player = self.env['auction.team.player'].sudo()
        if 'current_bid' not in Player._fields:
            return 0
        tid = tournament.id
        if not tid:
            return 0
        domain = [('tournament_id', '=', tid)]
        if 'current_bid_team_id' in Player._fields:
            domain = [
                ('tournament_id', '=', tid),
                '|',
                ('current_bid', '>', 0),
                ('current_bid_team_id', '!=', False),
            ]
        else:
            domain = [
                ('tournament_id', '=', tid),
                ('current_bid', '>', 0),
            ]
        try:
            to_clear = Player.search(domain)
        except Exception:
            return 0
        if not to_clear:
            return 0
        count = len(to_clear)
        try:
            to_clear.with_context(
                auction_skip_live_snapshot=True,
                mass_update=True,
            )._clear_live_bid()
        except Exception:
            # Last resort: direct SQL so restore still completes
            try:
                cr = self.env.cr
                if 'current_bid_team_id' in Player._fields:
                    cr.execute(
                        """
                        UPDATE auction_team_player
                           SET current_bid = 0,
                               current_bid_team_id = NULL
                         WHERE tournament_id = %s
                           AND (COALESCE(current_bid, 0) > 0
                                OR current_bid_team_id IS NOT NULL)
                        """,
                        (tid,),
                    )
                else:
                    cr.execute(
                        """
                        UPDATE auction_team_player
                           SET current_bid = 0
                         WHERE tournament_id = %s
                           AND COALESCE(current_bid, 0) > 0
                        """,
                        (tid,),
                    )
                to_clear.invalidate_cache(
                    ['current_bid', 'current_bid_team_id']
                    if 'current_bid_team_id' in Player._fields
                    else ['current_bid']
                )
            except Exception:
                return 0
        return count

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
        target = self.restore_to if self.restore_to in ('draft', 'auction') else 'auction'
        dest_label = _('Draft') if target == 'draft' else _('In Auction')
        # skip_reopen_live: do not put a random player on stage mid-restore;
        # clear_stage (when ticked) handles the projector / live board.
        restore_ctx = {
            'mass_update': True,
            'restore_to_state': target,
            'skip_reopen_live': True,
            'revoke_wizard': True,
        }

        if self.revoke_sold:
            sold = self._players('sold')
            if sold:
                sold.with_context(**restore_ctx).action_recall_auction_sold()
            parts.append(_('%s sold player(s) recalled to %s') % (len(sold), dest_label))

        if self.revoke_unsold:
            unsold = self._players('unsold')
            if unsold:
                if target == 'draft':
                    if hasattr(unsold, '_clear_live_bid'):
                        unsold._clear_live_bid()
                    unsold.write({'state': 'draft', 'is_on_stage': False})
                else:
                    unsold.with_context(**restore_ctx).action_auction()
            parts.append(_('%s unsold player(s) moved to %s') % (len(unsold), dest_label))

        if self.clear_stage:
            tournament.action_clear_stage()
            tournament.sudo().write({
                'stamp_player_id': False,
                'stamp_state': False,
                'stamp_expires_at': False,
            })
            parts.append(_('%s on-stage player(s) cleared') % self.stage_count)

        # Re-open live auction UI state without putting a random player on stage
        # (skip_reopen_live above). Clear Thank You / complete + leftover stamp.
        if self.revoke_sold or self.revoke_unsold or self.clear_stage or self.clear_history:
            tournament.sudo().write({
                'auction_declared_complete': False,
                'stamp_player_id': False,
                'stamp_state': False,
                'stamp_expires_at': False,
            })

        if self.clear_history:
            history_n = self.history_count
            tournament.with_context(revoke_wizard=True).action_clear_auction_history()
            bid_cleared = self._clear_tournament_live_bids(tournament)
            parts.append(_('%s history record(s) deleted') % history_n)
            parts.append(_('%s player bid(s) reset to default') % bid_cleared)

        message = _('Restore complete: %s.') % ', '.join(parts)
        if hasattr(self.env.user, 'notify_success'):
            self.env.user.notify_success(message)
        return {'type': 'ir.actions.act_window_close'}
