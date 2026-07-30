# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Keep existing tournaments code-protected after adding the new boolean.

    Odoo Boolean columns often land as NULL/False on existing rows; without
    this update every live board would suddenly become public.
    """
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'auction_tournament'
           AND column_name = 'live_board_code_protected'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE auction_tournament
           SET live_board_code_protected = TRUE
         WHERE live_board_code_protected IS DISTINCT FROM TRUE
        """
    )
    if cr.rowcount:
        _logger.info(
            "auction_module: set live_board_code_protected=TRUE on %s tournament(s).",
            cr.rowcount,
        )
