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


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    hammer_count = fields.Integer(
        string='Counter Hammer Strikes',
        default=3,
        help='Number of hammer strikes shown on owner consoles when Enable Counter is activated.',
    )
    counter_started_at = fields.Datetime(
        string='Counter Started At',
        copy=False,
        help='Set each time the auctioneer activates the countdown. '
             'Owner consoles detect the change and play the mallet animation.',
    )

    # ── Bid Revoke settings ───────────────────────────────────────────────
    revoke_enabled = fields.Boolean(
        string='Enable Bid Revoke',
        default=False,
        help='Allow owners to revoke (undo) their most recent bid during live auction. '
             'Can be toggled off at any time to immediately disable the feature.',
    )
    max_revokes = fields.Integer(
        string='Max Revokes (Global)',
        default=0,
        help='Total revokes allowed across ALL owners for this tournament. '
             '0 = feature disabled even if Enable Bid Revoke is on.',
    )
    revokes_used = fields.Integer(
        string='Revokes Used',
        default=0,
        readonly=True,
        copy=False,
        help='Running count of revokes consumed globally. Auto-incremented on each revoke.',
    )
