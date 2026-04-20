# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.web.controllers.main import Home, Session
from odoo.addons.website.controllers.main import Website
from odoo.http import request


class AuctionRootRedirect(Website):
    """Override website's '/' route to redirect to the Odoo backend."""

    @http.route('/', type='http', auth='public', website=True, sitemap=False)
    def index(self, **kw):
        return request.redirect('/web', code=302)


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


class AuctionLogoutController(Session):
    """Override logout to redirect with a ?logged_out=1 flag so the login page
    can display a goodbye animation before showing the sign-in form."""

    @http.route('/web/session/logout', type='http', auth='none')
    def logout(self, redirect='/web'):
        request.session.logout(keep_db=True)
        return request.redirect('/web/login?logged_out=1', 303)
