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

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Force the player-card landscape paperformat DPI to 85 on existing DBs.

    The player card is laid out in px on a custom mm page, so wkhtmltopdf's
    ``--dpi`` value controls the px -> mm scale. dpi=85 makes the card fill the
    page; the previously shipped dpi=90 renders the same px card ~6% smaller,
    leaving empty space at the bottom/right of the sheet.

    The paperformat record lives in a ``noupdate="1"`` data block, so a plain
    module upgrade never rewrites it (Odoo skips records whose stored
    ``ir_model_data.noupdate`` flag is True). This migration applies the fix
    directly, and only when the value still matches the old default (90) so any
    intentional manual tuning is preserved.
    """
    cr.execute(
        """
        UPDATE report_paperformat p
        SET dpi = 85
        FROM ir_model_data d
        WHERE d.model = 'report.paperformat'
          AND d.module = 'auction_module'
          AND d.name = 'paperformat_card_landscape'
          AND d.res_id = p.id
          AND p.dpi = 90
        """
    )
    if cr.rowcount:
        _logger.info(
            "auction_module: player-card landscape paperformat DPI set to 85 "
            "(%s record updated).",
            cr.rowcount,
        )
