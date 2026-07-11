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

class SetPlayerDraft(models.TransientModel):
    _name = 'auction.player.draft'

    player_ids = fields.Many2many('auction.team.player', 'player_draft_player_rel', 'auction_player_id', 'player_id', 'Selected Players')
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')

    @api.model
    def default_get(self, fields):
        defaults = super(SetPlayerDraft, self).default_get(fields)
        players = self.env['auction.team.player'].browse(self.env.context.get('active_ids', []))
        if any(player.state not in ["auction"] for player in players):
            raise ValidationError("Only the players in In Auction status can be reset to Draft! "
                                  "Please unselect the players which are not in In Auction status!")
        if self.env.context.get('active_ids', []):
            defaults.update({'player_ids': [(6, 0, self.env.context.get('active_ids', []))]})
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            defaults.update({'tournament_id': tournament_id.id})
        return defaults

    def button_set_to_draft(self):
        players = self.player_ids
        if any(player.state != "auction" for player in players):
            raise ValidationError("Only the players in In Auction status can be reset to Draft! "
                                  "Please unselect the players which are not in In Auction status!")
        players.write({'state': 'draft'})
        message = 'Selected Players are reset to Draft!'
        self.env.user.notify_success(message)



