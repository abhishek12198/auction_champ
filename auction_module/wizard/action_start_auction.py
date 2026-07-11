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
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class StartAuction(models.TransientModel):
    _name = 'auction.start.auction'

    max_points = fields.Integer(string='Total Purse Value')
    max_players = fields.Integer(string='Max no of players')
    base_point = fields.Integer(string="Base point for a player", default=1000)
    team_ids = fields.Many2many('auction.team', 'start_auction_team_rel', 'auction_start_id', 'team_id', 'Teams')
    tournament_id = fields.Many2one('auction.tournament', string='Tournament', readonly=True)
    max_limited = fields.Selection([('yes', 'Yes'), ('no', 'No')], default='no')
    max_point_player = fields.Integer('Max Point for a player')
    auction_bid_slab_ids = fields.One2many('auction.bid.slab', 'wizard_id', 'Slab')
    tier_limit_ids = fields.One2many('auction.start.auction.tier.limit', 'wizard_id', 'Tier Limits')

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
            res['tier_limit_ids'] = [
                (0, 0, {'tier_id': tier.id, 'max_players': 1, 'base_point': 0, 'max_call': 0})
                for tier in tiers
            ]
        return res

    @api.onchange('max_limited')
    def onchange_max_limited(self):
        if self.max_limited == 'no':
            self.max_points = 0

    @api.onchange('base_point')
    def onchange_base_point(self):
        if self.base_point <= 0:
            self.base_point = 1000

    def button_start_auction(self):
        auction_obj = self.env['auction.auction']
        auction_list = []
        if self.max_points <= 0:
            raise ValidationError("Points cannot be 0")
        if self.max_players <= 0:
            raise ValidationError("Number of players cannot be 0")

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
        return {
            'name': _('Players in Auction'),
            'view_mode': 'tree,form',
            'domain': [('state', '=', 'auction')],
            'res_model': 'auction.team.player',
            'type': 'ir.actions.act_window',
            'context': {'create': False},
        }

class AuctionBidSlab(models.TransientModel):

    _name = 'auction.bid.slab'

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
        help="Minimum bid for a player of this tier. Leave 0 to use the global base point.")
    max_call = fields.Integer(string='Max Call for a Player', default=0,
        help="Maximum bid allowed for a single player of this tier. Leave 0 for no cap.")
