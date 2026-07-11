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

class EditPlayerPoints(models.TransientModel):
    _name = 'auction.edit.player.point'

    points = fields.Integer()
    previous_points = fields.Integer()
    points_gain = fields.Integer()
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo = fields.Binary(related='player_id.photo')
    contact = fields.Char(related='player_id.contact')

    @api.model
    def default_get(self, fields):
        defaults = super(EditPlayerPoints, self).default_get(fields)
        if self.env.context.get('active_id', False):
            player_line = self.env['auction.auction.player'].browse(self.env.context.get('active_id', False))
            if player_line:
                defaults.update({'player_id': player_line.player_id.id, 'points': player_line.points, 'previous_points': player_line.points})

        return defaults

    @api.onchange('previous_points', 'points')
    def onchange_points(self):
        self.points_gain = self.previous_points - self.points

    def button_update_points(self):
        player_line_id = self.env.context.get('active_id', False)
        if player_line_id:
            player_line = self.env['auction.auction.player'].browse(player_line_id)
            player_line.points = self.points
            message = 'Points updated for the player '+player_line.player_id.name +' updated successfully'
            self.env.user.notify_success(message)


