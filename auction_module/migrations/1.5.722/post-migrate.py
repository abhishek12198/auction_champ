# -*- coding: utf-8 -*-
"""Recompute location full names with comma separators."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Location = env['auction.location'].with_context(active_test=False)
    level = Location.search([('parent_id', '=', False)])
    while level:
        level._compute_complete_name()
        level = Location.search([('parent_id', 'in', level.ids)])
    Location.flush()
