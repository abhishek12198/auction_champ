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


class AuctionWebsitePricing(models.Model):
    _name = 'auction.website.pricing'
    _description = 'AuctionChamp Website Pricing Plan'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Plan Name', required=True)
    subtitle = fields.Char(
        string='Subtitle',
        help='Short description shown below the plan name, e.g. "Perfect for small leagues"',
    )
    badge = fields.Char(
        string='Badge Label',
        help='Highlighted badge shown on the card, e.g. "Most Popular"',
    )
    features = fields.Text(
        string='Features',
        help='One feature per line. These are listed on the pricing card.',
    )
    contact_url = fields.Char(
        string='Contact / Sign-up URL',
        default='mailto:sales@auctionchamp.in',
    )
    is_highlighted = fields.Boolean(
        string='Highlight this plan',
        default=False,
        help='Visually emphasises this plan (larger card, coloured border).',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
