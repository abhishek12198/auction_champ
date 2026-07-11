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

import json
import os

_views_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'views'))
_jinja_env = None


def _get_jinja_env():
    """Build the Jinja2 environment lazily on first use to keep import-time
    side-effects to an absolute minimum."""
    global _jinja_env
    if _jinja_env is None:
        import jinja2
        _jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(_views_dir),
            autoescape=True,
        )
        _jinja_env.filters['json'] = json.dumps
    return _jinja_env


def _auction_render_template(self, **d):
    """Replacement for Database._render_template that uses the
    auction-themed Jinja2 template instead of Odoo's default."""
    import odoo
    import odoo.service.db
    from odoo import http
    from odoo.exceptions import AccessDenied
    from odoo.addons.web.controllers.main import db_monodb, DBNAME_PATTERN

    d.setdefault('manage', True)
    d['insecure'] = odoo.tools.config.verify_admin_password('admin')
    d['list_db'] = odoo.tools.config['list_db']
    d['langs'] = odoo.service.db.exp_list_lang()
    d['countries'] = odoo.service.db.exp_list_countries()
    d['pattern'] = DBNAME_PATTERN
    d['databases'] = []
    try:
        d['databases'] = http.db_list()
        d['incompatible_databases'] = odoo.service.db.list_db_incompatible(d['databases'])
    except AccessDenied:
        monodb = db_monodb()
        if monodb:
            d['databases'] = [monodb]
    return _get_jinja_env().get_template('database_manager.html').render(d)


# Patch the existing Database controller in-place.
# Doing this avoids defining a subclass (which would never be registered in
# controllers_per_module because it doesn't directly inherit from
# http.Controller) and avoids any route-registration conflicts.
# All heavy imports are deferred into _auction_render_template so that
# nothing can crash at module-load time.
from odoo.addons.web.controllers.main import Database  # noqa: E402
Database._render_template = _auction_render_template
