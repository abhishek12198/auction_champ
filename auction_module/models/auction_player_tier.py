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

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AuctionPlayerTier(models.Model):
    _name = 'auction.player.tier'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Auction Player Tier'

    name = fields.Char(string='Tier Name', required=True)
    description = fields.Char(string='Description')
    color = fields.Selection([
        ('#e74c3c', 'Red'),
        ('#e67e22', 'Orange'),
        ('#f39c12', 'Yellow'),
        ('#2ecc71', 'Green'),
        ('#1abc9c', 'Teal'),
        ('#3498db', 'Blue'),
        ('#2980b9', 'Dark Blue'),
        ('#9b59b6', 'Purple'),
        ('#e91e63', 'Pink'),
        ('#34495e', 'Dark'),
        ('#7f8c8d', 'Gray'),
        ('#ffffff', 'White'),
    ], string='Color', default='#3498db')
    is_an_icon_tier = fields.Boolean(string='Icon Tier', default=False)
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        ondelete='restrict',
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    def action_migrate_tier(self):
        self.ensure_one()
        return self.env['auction.migrate.tier'].with_context(active_id=self.id).action_open_wizard()

    @api.constrains('is_an_icon_tier', 'tournament_id')
    def _check_single_icon_tier(self):
        for record in self:
            if record.is_an_icon_tier:
                domain = [
                    ('is_an_icon_tier', '=', True),
                    ('id', '!=', record.id),
                ]
                if record.tournament_id:
                    domain.append(('tournament_id', '=', record.tournament_id.id))
                existing = self.search(domain, limit=1)
                if existing:
                    raise ValidationError(
                        'Only one tier can be marked as the Icon Tier per tournament. '
                        '"%s" is already set as the Icon Tier. '
                        'Please unmark it first before setting a new one.' % existing.name
                    )
