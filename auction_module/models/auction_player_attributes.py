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


class AuctionPlayerPosition(models.Model):
    _name = 'auction.player.position'
    _description = 'Football Playing Position'
    _order = 'sequence, id'

    name = fields.Char(string='Position', required=True)
    code = fields.Char(string='Code', help='Short code, e.g. GK, CB, ST.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AuctionPlayerStyle(models.Model):
    _name = 'auction.player.style'
    _description = 'Football Playing Style'
    _order = 'sequence, id'

    name = fields.Char(string='Playing Style', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AuctionPlayerStrength(models.Model):
    _name = 'auction.player.strength'
    _description = 'Football Player Strength'
    _order = 'sequence, id'

    name = fields.Char(string='Strength', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AuctionPlayerOtherAttribute(models.Model):
    _name = 'auction.player.other.attribute'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Football Player Other Attribute'
    _order = 'sequence, id'

    player_id = fields.Many2one(
        'auction.team.player', string='Player', required=True, ondelete='cascade', index=True)
    label = fields.Char(string='Label', required=True)
    value = fields.Char(string='Value')
    sequence = fields.Integer(default=10)


class AuctionTournamentAttributeLabel(models.Model):
    _name = 'auction.tournament.attribute.label'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Tournament Other Attribute Label'
    _order = 'sequence, id'

    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament', required=True, ondelete='cascade', index=True)
    label = fields.Char(
        string='Att-Label', required=True,
        help='Column / field label shown on the Excel template and player form '
             '(e.g. Club, Experience). Player rows store the matching Label-Value.')
    sequence = fields.Integer(default=10)
