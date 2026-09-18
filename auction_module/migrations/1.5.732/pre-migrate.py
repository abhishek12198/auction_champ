# -*- coding: utf-8 -*-
"""Drop an orphan Postgres composite type that blocks auction.location.

CREATE TABLE auction_location also creates type auction_location. If a
previous upgrade created the type and then rolled back the table, the next
-u fails with:

    duplicate key value violates unique constraint "pg_type_typname_nsp_index"
    DETAIL:  Key (typname, typnamespace)=(auction_location, 2200) already exists.

Drop the type only when the table itself is missing. Never drop it when the
table exists — CASCADE would drop the table and its data.
"""

import logging

_logger = logging.getLogger(__name__)

_TABLE = 'auction_location'


def migrate(cr, version):
    # Odoo table_exists() uses current_schema(); keep this upgrade in public
    # so auction_location is found and CREATE TABLE is skipped.
    cr.execute("SET search_path TO public")
    cr.execute("""
        SELECT EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relname = %s
               AND c.relkind IN ('r', 'v', 'm')
               AND n.nspname = current_schema()
        )
    """, (_TABLE,))
    if cr.fetchone()[0]:
        return

    cr.execute("""
        SELECT EXISTS (
            SELECT 1
              FROM pg_type t
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE t.typname = %s
               AND n.nspname = current_schema()
        )
    """, (_TABLE,))
    if not cr.fetchone()[0]:
        return

    cr.execute('DROP TYPE IF EXISTS "{}" CASCADE'.format(_TABLE))
    _logger.info(
        'auction_module 1.5.732: dropped orphan Postgres type %s '
        '(table was missing).',
        _TABLE,
    )
