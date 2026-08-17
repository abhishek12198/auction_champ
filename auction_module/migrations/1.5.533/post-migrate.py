# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rebuild register-roster snapshots so photo URLs pick up sz=rt."""
    env = api.Environment(cr, SUPERUSER_ID, {
        'auction_skip_tournament_security': True,
    })
    ids = env['auction.tournament'].sudo().search([]).ids
    if not ids:
        return
    try:
        from odoo.addons.auction_module.models.auction_live_snapshot_mixin import (
            mark_tournament_dirty,
        )
        mark_tournament_dirty(env, ids, ('reg',))
        _logger.info(
            'auction_module 1.5.533: marked %s tournament(s) dirty for roster photos.',
            len(ids),
        )
    except Exception:
        _logger.warning(
            'auction_module 1.5.533: could not dirty roster snapshots',
            exc_info=True,
        )
