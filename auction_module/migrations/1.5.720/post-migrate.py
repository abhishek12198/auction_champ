# -*- coding: utf-8 -*-
"""Map legacy venue text onto auction.location and drop the old column."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'auction_tournament'
           AND column_name = 'venue_legacy'
    """)
    if not cr.fetchone():
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Location = env['auction.location'].sudo()

    cr.execute("""
        SELECT id, venue_legacy
          FROM auction_tournament
         WHERE venue_legacy IS NOT NULL
           AND TRIM(venue_legacy) <> ''
    """)
    mapped = 0
    for tid, text in cr.fetchall():
        name = (text or '').strip().split('\n')[0][:128]
        if not name:
            continue
        loc = Location.search([('name', '=', name)], limit=1)
        if not loc:
            loc = Location.create({'name': name})
        cr.execute(
            "UPDATE auction_tournament SET venue = %s WHERE id = %s",
            (loc.id, tid),
        )
        mapped += 1

    cr.execute("ALTER TABLE auction_tournament DROP COLUMN venue_legacy")
    _logger.info(
        'auction_module 1.5.720: mapped %s tournament venue(s) to locations.',
        mapped,
    )
