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


class AuctionBidLog(models.Model):
    """Records every live bid placed via the Owner Console.
    Used to restore the previous bid state when an owner exercises a revoke.
    Entries are scoped to a player so revokes on one player never affect another.
    """
    _name = 'auction.bid.log'
    _description = 'Live Auction Bid History'
    _order = 'id asc'

    player_id = fields.Many2one(
        'auction.team.player', required=True, ondelete='cascade', index=True,
    )
    team_id = fields.Many2one(
        'auction.team', required=True, ondelete='cascade',
    )
    bid_amount = fields.Integer(required=True)
    tournament_id = fields.Many2one(
        'auction.tournament', required=True, ondelete='cascade', index=True,
    )
    timestamp = fields.Datetime(default=fields.Datetime.now, readonly=True)
