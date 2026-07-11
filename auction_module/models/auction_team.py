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
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionTeam(models.Model):
    _name = 'auction.team'
    _inherit = ['auction.image.compress.mixin', 'auction.tournament.security.mixin']

    _compressible_image_fields = {
        'logo': (400, 400, 82, 'JPEG'),
    }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    active = fields.Boolean(default=True)
    name = fields.Char(string="Team Name", required=True)
    logo = fields.Binary(string="Team Logo",
                            help="Add team logo")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    manager = fields.Char('Owner')
    key_player_ids = fields.Many2many('auction.team.player', 'team_player_rel', 'team_id', 'player_id', 'Icon Players')
