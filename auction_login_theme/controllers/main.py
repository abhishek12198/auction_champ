# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.web.controllers.main import Home
from odoo.http import request


class AuctionLoginController(Home):
    """Override the default Odoo web login to render our custom sporty theme."""

    @http.route('/web/login', type='http', auth='none', sitemap=False)
    def web_login(self, redirect=None, **kw):
        # Parent handles: ensure_db, CSRF, session auth, success redirect, error state
        response = super().web_login(redirect=redirect, **kw)
        # Only swap on GET / failed-POST — success returns a werkzeug redirect (no .template)
        if hasattr(response, 'template') and response.template == 'web.login':
            response.template = 'auction_login_theme.login'
        return response
