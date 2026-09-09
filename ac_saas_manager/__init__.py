# -*- coding: utf-8 -*-
from . import controllers
from . import models
from . import wizard


def post_init_hook(cr, registry):
    """Repair organiser ↔ tournament links, plan groups, and registration caps."""
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    accounts = env['ac.saas.account'].search([])
    accounts._sync_user_tournament_links()
    accounts._sync_user_groups()
    env['auction.tournament']._saas_repair_max_registrations()
