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
    """Privacy flags for the public registered-players popup."""
    for col in ('expose_registered_org_id', 'expose_registered_address'):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'auction_tournament'
               AND column_name = %s
            """,
            (col,),
        )
        if cr.fetchone():
            continue
        cr.execute(
            """
            ALTER TABLE auction_tournament
                ADD COLUMN %s boolean DEFAULT FALSE
            """ % col
        )
        cr.execute(
            """
            UPDATE auction_tournament
               SET %s = FALSE
             WHERE %s IS NULL
            """ % (col, col)
        )
        _logger.info(
            "auction_module: added auction_tournament.%s (default FALSE).",
            col,
        )
