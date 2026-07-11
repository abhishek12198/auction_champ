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

class SetKeyPlayer(models.TransientModel):
    _name = 'auction.set.key.player'


    team_id = fields.Many2one('auction.team', 'Team')
    team_selection = fields.Selection(selection='_get_team_selection', string='Select Team')
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo  = fields.Binary()
    team_logo = fields.Binary()

    def _get_team_selection(self):
        teams = self.env['auction.team'].search([], order='name asc')
        return [(str(t.id), t.name) for t in teams]

    @api.model
    def default_get(self, fields):
        defaults = super(SetKeyPlayer, self).default_get(fields)
        if self.env.context.get('active_id', False):
            player = self.env['auction.team.player'].browse(self.env.context.get('active_id', False))
            defaults.update({'player_photo': player.photo,'player_id': self.env.context.get('active_id', False)})
        return defaults

    @api.onchange('team_selection')
    def onchange_team_selection(self):
        if self.team_selection:
            self.team_id = int(self.team_selection)
            self.team_logo = self.team_id.logo
        else:
            self.team_id = False
            self.team_logo = False

    @api.onchange('team_id')
    def onchange_team(self):
        if self.team_id:
            self.team_logo = self.team_id.logo
        else:
            self.team_logo = False

    def button_set_keyplayer(self):
        player_id = self.env.context.get('active_id', False)
        if player_id:
            player = self.player_id
            team = self.team_id
            # Fallback: if onchange value was flushed during form-save,
            # reconstruct team from team_selection (always persisted as a simple Selection)
            if not team and self.team_selection:
                team = self.env['auction.team'].browse(int(self.team_selection))

            if not team:
                raise UserError('Please select a team before confirming.')
            # Find the icon tier (only one should exist due to constraint)
            icon_tier = self.env['auction.player.tier'].search([('is_an_icon_tier', '=', True)], limit=1)
            if not icon_tier:
                raise UserError(
                    'No Icon Tier is configured. Please mark one tier as "Icon Tier" in Player Tiers before promoting a player.'
                )

            player.write({
                'icon_player': True,
                'state': 'sold',
                'assigned_team_id': team.id,
                'previous_tier_id': player.tier_id.id if player.tier_id else False,
                'tier_id': icon_tier.id,
            })

            team.key_player_ids = [(4, player.id)]

            message = player.name + ' set as Icon Player for team ' + team.name + ' and moved to "%s" tier successfully!' % icon_tier.name
            self.env.user.notify_success(message)


