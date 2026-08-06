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
    """Ensure show_registration_capacity exists (default TRUE) on existing DBs."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'auction_tournament'
           AND column_name = 'show_registration_capacity'
        """
    )
    if cr.fetchone():
        return
    cr.execute(
        """
        ALTER TABLE auction_tournament
            ADD COLUMN show_registration_capacity boolean
            DEFAULT TRUE
        """
    )
    cr.execute(
        """
        UPDATE auction_tournament
           SET show_registration_capacity = TRUE
         WHERE show_registration_capacity IS NULL
        """
    )
    _logger.info(
        "auction_module: added auction_tournament.show_registration_capacity "
        "(default TRUE)."
    )
