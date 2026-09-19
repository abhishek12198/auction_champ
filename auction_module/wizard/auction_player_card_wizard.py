# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AuctionPlayerCardWizardLine(models.TransientModel):
    _name = 'auction.player.card.wizard.line'
    _description = 'Player Card Print Line'
    _order = 'player_sl_no, id'

    wizard_id = fields.Many2one(
        'auction.player.card.wizard', required=True, ondelete='cascade',
    )
    player_id = fields.Many2one(
        'auction.team.player', string='Player', required=True,
    )
    print_ok = fields.Boolean(string='Print', default=True)
    player_sl_no = fields.Integer(related='player_id.sl_no', string='Sl No')
    player_name = fields.Char(related='player_id.name', string='Name')
    player_state = fields.Selection(related='player_id.state', string='Status')
    player_role = fields.Char(related='player_id.role', string='Role')
    player_photo = fields.Binary(related='player_id.photo', string='Photo')


class AuctionPlayerCardWizard(models.TransientModel):
    _name = 'auction.player.card.wizard'
    _description = 'Print Player Cards'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, readonly=True,
    )
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', string='Sport', readonly=True,
    )
    include_draft = fields.Boolean(string='Registered', default=True)
    include_auction = fields.Boolean(string='In Auction', default=True)
    include_sold = fields.Boolean(string='Sold', default=True)
    include_unsold = fields.Boolean(string='Unsold', default=True)
    line_ids = fields.One2many(
        'auction.player.card.wizard.line', 'wizard_id', string='Players',
    )
    player_count = fields.Integer(compute='_compute_counts')
    selected_count = fields.Integer(compute='_compute_counts')
    draft_count = fields.Integer(compute='_compute_counts')
    auction_count = fields.Integer(compute='_compute_counts')
    sold_count = fields.Integer(compute='_compute_counts')
    unsold_count = fields.Integer(compute='_compute_counts')

    @api.depends(
        'line_ids.print_ok', 'line_ids.player_state',
        'include_draft', 'include_auction', 'include_sold', 'include_unsold',
    )
    def _compute_counts(self):
        for wiz in self:
            lines = wiz.line_ids
            wiz.player_count = len(lines)
            wiz.selected_count = len(lines.filtered('print_ok'))
            wiz.draft_count = len(lines.filtered(lambda l: l.player_state == 'draft'))
            wiz.auction_count = len(lines.filtered(lambda l: l.player_state == 'auction'))
            wiz.sold_count = len(lines.filtered(lambda l: l.player_state == 'sold'))
            wiz.unsold_count = len(lines.filtered(lambda l: l.player_state == 'unsold'))

    def _player_env(self):
        return self.env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
            active_test=False,
        )

    def _selected_states(self):
        self.ensure_one()
        states = []
        if self.include_draft:
            states.append('draft')
        if self.include_auction:
            states.append('auction')
        if self.include_sold:
            states.append('sold')
        if self.include_unsold:
            states.append('unsold')
        return states

    def _search_players(self, tournament_id, states):
        if not tournament_id or not states:
            return self._player_env().browse()
        return self._player_env().search(
            [('tournament_id', '=', tournament_id), ('state', 'in', states)],
            order='sl_no, name, id',
        )

    def _line_commands(self, players, keep=None):
        keep = keep or {}
        return [(5, 0, 0)] + [
            (0, 0, {
                'player_id': player.id,
                'print_ok': keep.get(player.id, True),
            })
            for player in players
        ]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tid = res.get('tournament_id') or self.env.context.get('default_tournament_id')
        if tid:
            res['tournament_id'] = tid
            include = {
                'include_draft': res.get('include_draft', True),
                'include_auction': res.get('include_auction', True),
                'include_sold': res.get('include_sold', True),
                'include_unsold': res.get('include_unsold', True),
            }
            states = []
            if include['include_draft']:
                states.append('draft')
            if include['include_auction']:
                states.append('auction')
            if include['include_sold']:
                states.append('sold')
            if include['include_unsold']:
                states.append('unsold')
            players = self._search_players(tid, states)
            res['line_ids'] = [(0, 0, {'player_id': p.id, 'print_ok': True}) for p in players]
        return res

    @api.onchange('include_draft', 'include_auction', 'include_sold', 'include_unsold')
    def _onchange_include(self):
        keep = {line.player_id.id: line.print_ok for line in self.line_ids if line.player_id}
        players = self._search_players(self.tournament_id.id, self._selected_states())
        self.line_ids = self._line_commands(players, keep)

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({'print_ok': True})
        return self._reopen()

    def action_select_none(self):
        self.ensure_one()
        self.line_ids.write({'print_ok': False})
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Print Player Cards'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        self.ensure_one()
        players = self.line_ids.filtered('print_ok').mapped('player_id')
        if not players:
            raise UserError(_('Select at least one player to print.'))
        return players.sudo().print_player_cards()
