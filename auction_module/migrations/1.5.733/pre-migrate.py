# -*- coding: utf-8 -*-
"""Force public search_path so existing auction_location is visible to Odoo."""


def migrate(cr, version):
    cr.execute("SET search_path TO public")
