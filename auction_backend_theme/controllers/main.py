import json
import os
import jinja2
import odoo
import odoo.service.db
from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import db_list, request
from odoo.addons.web.controllers.main import Database, db_monodb, DBNAME_PATTERN

_views_dir = os.path.join(os.path.dirname(__file__), '..', 'views')
_auction_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_views_dir),
    autoescape=True,
)
_auction_jinja_env.filters['json'] = json.dumps


class AuctionDatabase(Database):
    """Override the Database controller to render the custom auction-themed
    database manager page instead of the default Odoo-branded one."""

    def _render_template(self, **d):
        d.setdefault('manage', True)
        d['insecure'] = odoo.tools.config.verify_admin_password('admin')
        d['list_db'] = odoo.tools.config['list_db']
        d['langs'] = odoo.service.db.exp_list_lang()
        d['countries'] = odoo.service.db.exp_list_countries()
        d['pattern'] = DBNAME_PATTERN
        d['databases'] = []
        try:
            d['databases'] = db_list()
            d['incompatible_databases'] = odoo.service.db.list_db_incompatible(d['databases'])
        except AccessDenied:
            monodb = db_monodb()
            if monodb:
                d['databases'] = [monodb]
        return _auction_jinja_env.get_template('database_manager.html').render(d)
