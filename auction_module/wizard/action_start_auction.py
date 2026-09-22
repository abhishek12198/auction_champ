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

import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions

class StartAuction(models.TransientModel):
    _name = 'auction.start.auction'
    _description = 'Start Auction'

    max_points = fields.Integer(string='Total Purse Value')
    max_players = fields.Integer(string='Max no of players')
    base_point = fields.Integer(
        string="Global base point",
        default=0,
        help="Default minimum bid and purse reserve. Any tier with Base Point 0 "
             "uses this value. Set it here, or set a Base Point on every tier — "
             "nothing is assumed.",
    )
    team_ids = fields.Many2many('auction.team', 'start_auction_team_rel', 'auction_start_id', 'team_id', 'Teams')
    tournament_id = fields.Many2one('auction.tournament', string='Tournament', readonly=True)
    max_limited = fields.Selection([('yes', 'Yes'), ('no', 'No')], default='no')
    max_point_player = fields.Integer('Max Point for a player')
    auction_bid_slab_ids = fields.One2many('auction.bid.slab', 'wizard_id', 'Slab')
    tier_limit_ids = fields.One2many('auction.start.auction.tier.limit', 'wizard_id', 'Tier Limits')
    point_unit_name = fields.Char(
        related='tournament_id.point_unit_id.name',
        readonly=True,
    )
    team_count = fields.Integer(compute='_compute_team_count')

    @api.model
    def default_get(self, fields_list):
        res = super(StartAuction, self).default_get(fields_list)
        # When launched from a tournament form, pre-scope the wizard to that
        # tournament and default the team list to that tournament's teams only.
        tournament = self.env['auction.tournament']
        tournament_id = self.env.context.get('default_tournament_id') or self.env.context.get('active_tournament_id')
        if tournament_id:
            tournament = self.env['auction.tournament'].browse(tournament_id)
            if tournament.exists():
                res['tournament_id'] = tournament.id
                if 'team_ids' in fields_list:
                    res['team_ids'] = [(6, 0, tournament.team_ids.ids)]
        # Only offer tiers that belong to this tournament (fall back to all when
        # the wizard is opened without a tournament context).
        tier_domain = [('is_an_icon_tier', '!=', True)]
        if tournament:
            tier_domain.append(('tournament_id', '=', tournament.id))
        tiers = self.env['auction.player.tier'].search(tier_domain)
        if tiers and 'tier_limit_ids' in fields_list:
            single = len(tiers) == 1
            max_players = res.get('max_players') or 0
            base_point = res.get('base_point') or 0
            res['tier_limit_ids'] = [
                (0, 0, {
                    'tier_id': tier.id,
                    'max_players': max_players if single and max_players else 1,
                    'base_point': base_point if single and base_point else 0,
                    'max_call': 0,
                })
                for tier in tiers
            ]
        return res

    @api.onchange('max_limited')
    def onchange_max_limited(self):
        if self.max_limited == 'no':
            self.max_points = 0

    @api.onchange('base_point')
    def onchange_base_point(self):
        if self.base_point < 0:
            self.base_point = 0
        self._apply_single_tier_defaults()
        self._apply_first_slab_from()

    @api.onchange('max_players')
    def onchange_max_players(self):
        self._apply_single_tier_defaults()

    @api.onchange('auction_bid_slab_ids')
    def onchange_first_slab_from(self):
        self._apply_first_slab_from()
        self._chain_slab_from_amounts()

    def _apply_single_tier_defaults(self):
        """One tier = squad size and global base, so the line does not stay at 1 / 0."""
        if len(self.tier_limit_ids) != 1:
            return
        line = self.tier_limit_ids[0]
        if self.max_players > 0:
            line.max_players = self.max_players
        if self.base_point > 0:
            line.base_point = self.base_point

    def _apply_first_slab_from(self):
        """First slab From starts at the global base when the user left it empty."""
        if not self.auction_bid_slab_ids or self.base_point <= 0:
            return
        first = self.auction_bid_slab_ids[0]
        if not first.from_amount:
            first.from_amount = self.base_point

    @api.depends('team_ids')
    def _compute_team_count(self):
        for rec in self:
            rec.team_count = len(rec.team_ids)

    def _chain_slab_from_amounts(self):
        """Each slab's From must equal the previous Until (rows after the first)."""
        prev_to = 0
        for index, line in enumerate(self.auction_bid_slab_ids):
            if index == 0:
                if not line.from_amount and self.base_point:
                    line.from_amount = self.base_point
            elif prev_to:
                # Always chain — From is locked in the wizard for row 2+.
                line.from_amount = prev_to
            prev_to = line.to_amount or 0

    def button_start_auction(self):
        self._chain_slab_from_amounts()
        auction_obj = self.env['auction.auction']
        auction_list = []
        if self.max_points <= 0:
            raise ValidationError("Points cannot be 0")
        if self.max_players <= 0:
            raise ValidationError("Number of players cannot be 0")
        if self.base_point < 0:
            raise ValidationError("Global base point cannot be negative.")
        unset_tiers = self.tier_limit_ids.filtered(lambda t: t.base_point <= 0)
        if self.tier_limit_ids:
            if unset_tiers and self.base_point <= 0:
                raise ValidationError(
                    "Set a Global base point, or enter a Base Point on every tier. "
                    "Tiers with Base Point 0 use the global value — nothing is filled in for you."
                )
        elif self.base_point <= 0:
            raise ValidationError(
                "Set a Global base point. It is the minimum bid and the amount "
                "reserved for remaining squad slots."
            )

        if not len(self.team_ids) >= 2:
            raise ValidationError("Select atleast two teams")
        # Derive the tournament from the selected teams (each team belongs to a
        # tournament). Using the first "active" tournament is wrong when more than
        # one tournament is active at a time, because it silently assigns the
        # auction records to the wrong tournament.
        team_tournaments = self.team_ids.mapped('tournament_id')
        if len(team_tournaments) > 1:
            raise ValidationError("All selected teams must belong to the same tournament.")
        tournament_id = self.tournament_id or team_tournaments[:1] or self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        bid_slab_data = [(0, 0, {'from_amount': line.from_amount, 'to_amount': line.to_amount,'increment': line.increment}) for line in self.auction_bid_slab_ids]
        tier_limit_data = [(0, 0, {'tier_id': line.tier_id.id, 'max_players': line.max_players, 'base_point': line.base_point, 'max_call': line.max_call}) for line in self.tier_limit_ids]
        if self.team_ids:
            existing_auctions  = auction_obj.search([('team_id', 'in', self.team_ids.ids)])
            if existing_auctions:
                raise ValidationError("Auction rules has been created already for the teams. Please delete the auction records and continue creating.")
            for team in self.team_ids:
                auction_data = {
                    'team_id': team.id,
                    'total_point': self.max_points,
                    'max_players': self.max_players,
                    'base_point': self.base_point,
                    'auction_bid_slab_ids': bid_slab_data,
                    'tier_limit_ids': tier_limit_data,
                }

                auction_data.update({'tournament_id': team.tournament_id.id or tournament_id.id})
                auction_list.append(auction_data)

        if auction_list:
            auction_obj.create(auction_list)
        self.env.user.notify_success('Auction process initiated successfully for the selected teams!')
        tid = tournament_id.id if tournament_id else False
        return {
            'name': _('Auction List'),
            'type': 'ir.actions.act_window',
            'res_model': 'auction.auction',
            'view_mode': 'kanban,tree,form',
            'views': [(False, 'kanban'), (False, 'tree'), (False, 'form')],
            'search_view_id': self.env.ref('auction_module.view_auction_auction_search').id,
            'domain': [('tournament_id', '=', tid)] if tid else [],
            'context': {
                'default_tournament_id': tid,
                'create': False,
            },
            'target': 'current',
        }

class AuctionBidSlab(models.TransientModel):

    _name = 'auction.bid.slab'
    _description = 'Start Auction Bid Slab'

    wizard_id = fields.Many2one('auction.start.auction', ondelete='cascade')

    from_amount = fields.Integer(required=True)
    to_amount = fields.Integer(required=True)
    increment = fields.Integer(required=True)


class AuctionStartAuctionTierLimit(models.TransientModel):
    _name = 'auction.start.auction.tier.limit'
    _description = 'Auction Setup Tier Limit'

    wizard_id = fields.Many2one('auction.start.auction', ondelete='cascade')
    tier_id = fields.Many2one('auction.player.tier', string='Tier', required=True)
    max_players = fields.Integer(string='Max Players per Team', required=True, default=1)
    base_point = fields.Integer(string='Base Point', default=0,
        help="Minimum bid for this tier. 0 = use Global base point from this wizard.")
    max_call = fields.Integer(string='Max Call for a Player', default=0,
        help="Maximum bid allowed for a single player of this tier. Leave 0 for no cap.")
