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


class EditPlayerPoints(models.TransientModel):
    _name = 'auction.edit.player.point'
    _description = 'Edit Sold Player Value'

    points = fields.Integer(string='New Value')
    previous_points = fields.Integer(string='Previous Value')
    points_gain = fields.Integer(string='Difference')
    previous_points_display = fields.Char(string='Previous (display)', readonly=True)
    points_gain_display = fields.Char(string='Difference (display)', readonly=True)
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo = fields.Binary(related='player_id.photo')
    contact = fields.Char(related='player_id.contact')
    tournament_id = fields.Many2one('auction.tournament', string='Tournament', readonly=True)
    point_unit_label = fields.Char(string='Unit', readonly=True)
    point_unit_symbol = fields.Char(string='Symbol', readonly=True)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if not active_id:
            return defaults
        player_line = self.env['auction.auction.player'].browse(active_id)
        if not player_line.exists():
            return defaults
        tournament = player_line.auction_id.tournament_id
        unit = tournament.get_point_unit() if tournament else False
        unit_name = unit.name if unit else 'Points'
        unit_symbol = unit.symbol if unit else 'PTS'
        pts = player_line.points or 0
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        defaults.update({
            'player_id': player_line.player_id.id,
            'points': pts,
            'previous_points': pts,
            'previous_points_display': fmt(pts),
            'points_gain': 0,
            'points_gain_display': fmt(0),
            'tournament_id': tournament.id if tournament else False,
            'point_unit_label': unit_name,
            'point_unit_symbol': unit_symbol,
        })
        return defaults

    def _fmt(self, amount):
        self.ensure_one()
        if self.tournament_id:
            return self.tournament_id.format_points(amount or 0)
        return '{:,}'.format(int(amount or 0))

    @api.onchange('previous_points', 'points')
    def onchange_points(self):
        self.points_gain = (self.previous_points or 0) - (self.points or 0)
        self.previous_points_display = self._fmt(self.previous_points)
        # Show signed difference with unit formatting on absolute value
        gain = self.points_gain or 0
        formatted = self._fmt(abs(gain))
        if gain > 0:
            self.points_gain_display = '+%s (saved)' % formatted
        elif gain < 0:
            self.points_gain_display = '-%s (extra)' % formatted
        else:
            self.points_gain_display = formatted

    def button_update_points(self):
        self.ensure_one()
        player_line_id = self.env.context.get('active_id', False)
        if not player_line_id:
            return True
        player_line = self.env['auction.auction.player'].browse(player_line_id)
        player_line.points = self.points
        unit = self.point_unit_label or 'value'
        message = '%s updated to %s successfully' % (
            player_line.player_id.name,
            self._fmt(self.points),
        )
        self.env.user.notify_success(message=message, title='%s Updated' % unit)
        return True
