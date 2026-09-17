# -*- coding: utf-8 -*-
"""Keep old free-text venue values before the field becomes a Many2one."""


def migrate(cr, version):
    cr.execute("""
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name = 'auction_tournament'
           AND column_name = 'venue'
    """)
    row = cr.fetchone()
    if not row:
        return
    if row[0] in ('integer', 'int4', 'int8'):
        return
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'auction_tournament'
           AND column_name = 'venue_legacy'
    """)
    if cr.fetchone():
        return
    cr.execute(
        "ALTER TABLE auction_tournament RENAME COLUMN venue TO venue_legacy"
    )
