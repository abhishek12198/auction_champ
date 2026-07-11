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

from odoo import models, fields


class AuctionAdvertiser(models.Model):
    _name = 'auction.advertiser'
    _description = 'Auction Advertiser / Sponsor'
    _order = 'sequence, id'
    _inherit = ['auction.image.compress.mixin', 'auction.tournament.security.mixin']

    _compressible_image_fields = {
        'image': (1200, 500, 82, 'JPEG'),
    }

    name = fields.Char(string='Advertiser / Sponsor Name', required=True)
    image = fields.Binary(
        string='Image / Banner',
        required=True,
        help='Upload a sponsor logo or advertisement banner. '
             'Recommended size: 800×300 px (landscape). PNG or JPG.',
    )
    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament',
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='Display Order', default=10)
    active = fields.Boolean(default=True)
