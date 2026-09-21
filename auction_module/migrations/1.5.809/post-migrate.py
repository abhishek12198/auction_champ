# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import logging
import re
import unicodedata

_logger = logging.getLogger(__name__)

_RESERVED = frozenset({'admin', 'players', 'events', 'check_mobile'})


def _slugify(text):
    value = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    value = value.lower()
    value = re.sub(r'[^\w\s-]', '', value)
    value = re.sub(r'[\s_]+', '-', value)
    return value.strip('-') or 'tier'


def migrate(cr, version):
    """Add per-tier registration columns (slug + max) and backfill slugs."""
    cr.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'auction_player_tier'
        )
    """)
    if not cr.fetchone()[0]:
        return

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'auction_player_tier'
           AND column_name = 'registration_slug'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE auction_player_tier
                ADD COLUMN registration_slug varchar
        """)
        _logger.info('auction_module 1.5.809: added registration_slug')

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'auction_player_tier'
           AND column_name = 'max_registrations'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE auction_player_tier
                ADD COLUMN max_registrations integer DEFAULT 0
        """)
        cr.execute("""
            UPDATE auction_player_tier
               SET max_registrations = 0
             WHERE max_registrations IS NULL
        """)
        _logger.info('auction_module 1.5.809: added max_registrations')

    cr.execute("""
        SELECT id, name, tournament_id
          FROM auction_player_tier
         WHERE registration_slug IS NULL OR registration_slug = ''
    """)
    rows = cr.fetchall()
    if rows:
        cr.execute("""
            SELECT tournament_id, registration_slug
              FROM auction_player_tier
             WHERE registration_slug IS NOT NULL AND registration_slug <> ''
        """)
        used = {}
        for tournament_id, slug in cr.fetchall():
            used.setdefault(tournament_id or 0, set()).add(slug)
        for tier_id, name, tournament_id in rows:
            base = _slugify(name)
            if base in _RESERVED:
                base = '%s-tier' % base
            bucket = used.setdefault(tournament_id or 0, set())
            slug = base
            n = 2
            while slug in bucket:
                slug = '%s-%s' % (base, n)
                n += 1
            bucket.add(slug)
            cr.execute(
                "UPDATE auction_player_tier SET registration_slug = %s WHERE id = %s",
                (slug, tier_id),
            )
        _logger.info(
            'auction_module 1.5.809: backfilled registration_slug on %s tier(s)',
            len(rows),
        )

    cr.execute("""
        SELECT 1 FROM pg_indexes
         WHERE tablename = 'auction_player_tier'
           AND indexname = 'auction_player_tier_registration_slug_tournament_uniq'
    """)
    if not cr.fetchone():
        try:
            cr.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                    auction_player_tier_registration_slug_tournament_uniq
                    ON auction_player_tier (tournament_id, registration_slug)
            """)
        except Exception:
            _logger.warning(
                'auction_module 1.5.809: unique index skipped (duplicates?)',
                exc_info=True,
            )
