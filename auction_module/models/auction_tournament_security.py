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

from odoo import api, models
from odoo.osv import expression


class AuctionTournamentSecurityMixin(models.AbstractModel):
    """Scope auction records by the user's Active Tournament.

    - Auction Administrator (and sudo): see all records.
    - Every other user: only records for ``user.tournament_id``.
    """
    _name = 'auction.tournament.security.mixin'
    _description = 'Auction Tournament Security Mixin'

    def _auction_is_admin(self):
        return (
            self.env.su
            or self.env.user.has_group('auction_module.group_auction_group_admin')
        )

    def _auction_tournament_field(self):
        """Domain field path used to scope this model."""
        mapping = {
            'auction.tournament': 'id',
            'auction.auction.player': 'auction_id.tournament_id',
            'auction.auction.bid.slab': 'auction_id.tournament_id',
            'auction.auction.tier.limit': 'auction_id.tournament_id',
            'auction.player.other.attribute': 'player_id.tournament_id',
        }
        return mapping.get(self._name, 'tournament_id')

    def _auction_tournament_security_domain(self):
        if self._auction_is_admin():
            return []
        tid = self.env.user.tournament_id.id
        if not tid:
            return [('id', '=', False)]
        return [(self._auction_tournament_field(), '=', tid)]

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = expression.AND([args or [], self._auction_tournament_security_domain()])
        return super()._search(
            args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid,
        )
