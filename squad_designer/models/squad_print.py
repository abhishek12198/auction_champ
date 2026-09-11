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

from odoo import fields, models

TEMPLATES = [
    ('ipl_classic',       'IPL Classic'),
    ('modern_gradient',   'Modern Gradient'),
    ('bbl_bold',          'Big Bash Bold'),
    ('test_classic',      'Test Classic'),
    ('minimalist_pro',    'Minimalist Pro'),
]


class SquadPrint(models.Model):
    _name = 'squad.print'
    _description = 'Squad Print Designer'
    _order = 'write_date desc'
    _rec_name = 'name'

    name = fields.Char('Title / Tournament', required=True)
    team_name = fields.Char('Team Name', required=True)
    team_logo = fields.Binary('Team Logo', attachment=True)
    team_logo_fname = fields.Char()
    season = fields.Char('Season / Year', help='e.g. IPL 2025')
    tagline = fields.Char('Team Tagline', help='Short team motto or tagline')
    team_color_primary = fields.Char(
        'Primary Color', default='#003087',
        help='Hex color used as primary brand color in the card')
    team_color_secondary = fields.Char(
        'Secondary Color', default='#FFD700',
        help='Hex color used as accent / secondary brand color')
    template = fields.Selection(
        TEMPLATES, string='Print Template',
        default='ipl_classic', required=True)
    player_ids = fields.One2many('squad.print.player', 'squad_id', 'Players')
    player_count = fields.Integer(compute='_compute_player_count', store=False)

    def _compute_player_count(self):
        for rec in self:
            rec.player_count = len(rec.player_ids)

    def action_preview(self):
        """Open the squad card preview in a new browser tab."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/squad/preview/%d' % self.id,
            'target': 'new',
        }


class SquadPrintPlayer(models.Model):
    _name = 'squad.print.player'
    _description = 'Squad Player'
    _order = 'sequence, id'

    squad_id = fields.Many2one(
        'squad.print', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Player Name', required=True)
    role = fields.Char('Role', help='e.g. Batsman, Bowler, All-rounder, WK')
    category_id = fields.Many2one(
        'squad.player.category', 'Category',
        help='e.g. Foreign, Domestic, Capped, Uncapped')
    photo = fields.Binary('Photo', attachment=True)
    photo_fname = fields.Char()
    jersey_no = fields.Char('Jersey #', size=4)
    nationality = fields.Char('Nationality')
    is_captain = fields.Boolean('Captain')
    is_vc = fields.Boolean('Vice Captain')
