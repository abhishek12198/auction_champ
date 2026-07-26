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
    """Scope auction records by the user's assigned tournament(s).

    - Auction Administrator (and sudo): see all records.
    - Every other user: records for Active Tournament **and** Organizer M2M
      (``tournament_id`` ∪ ``tournament_ids``).

    Using only Active Tournament left organizers who were assigned via the
    tournament Organizers field (M2M) but missing Active Tournament with
    empty player/team lists while dashboards (sudo) still showed counts.
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

    def _auction_allowed_tournament_ids(self):
        """Union of Active Tournament and Organizer M2M assignments."""
        user = self.env.user
        tids = set(user.tournament_ids.ids)
        if user.tournament_id:
            tids.add(user.tournament_id.id)
        return list(tids)

    def _auction_tournament_security_domain(self):
        # Public HTTP pages (Bid Summary, etc.) pass this context flag after
        # switching DB via _with_db so searches are never emptied by SaaS /
        # organizer tournament scopes.
        if self.env.context.get('auction_skip_tournament_security'):
            return []
        if self._auction_is_admin():
            return []
        tids = self._auction_allowed_tournament_ids()
        if not tids:
            return [('id', '=', False)]
        return [(self._auction_tournament_field(), 'in', tids)]

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = expression.AND([args or [], self._auction_tournament_security_domain()])
        return super()._search(
            args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid,
        )

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        # read_group does not go through _search — apply the same scope here so
        # tournament stat buttons match list views.
        domain = expression.AND([domain or [], self._auction_tournament_security_domain()])
        return super().read_group(
            domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy,
        )
