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

from odoo import api, models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    auction_team_id = fields.Many2one(
        'auction.team',
        string='My Auction Team',
        help='Assign this user to a team so they can use the Owner Console.',
    )

    def _sync_tournament_from_auction_team(self):
        """Keep Active Tournament aligned with the assigned owner team."""
        for user in self:
            team = user.auction_team_id
            if not team or not team.tournament_id:
                continue
            vals = {}
            if user.tournament_id.id != team.tournament_id.id:
                vals['tournament_id'] = team.tournament_id.id
            if team.tournament_id.id not in user.tournament_ids.ids:
                vals['tournament_ids'] = [(4, team.tournament_id.id)]
            if vals:
                user.with_context(skip_tournament_sync=True).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._sync_tournament_from_auction_team()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'auction_team_id' in vals:
            self._sync_tournament_from_auction_team()
        return res
