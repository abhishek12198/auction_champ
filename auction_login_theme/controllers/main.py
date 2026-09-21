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

from odoo import http
from odoo.addons.web.controllers.main import Home, Session, ensure_db
from odoo.addons.website.controllers.main import Website
from odoo.http import request


def _safe_post_login_redirect(redirect=None):
    """Return a same-site path to open after an already-authenticated visit."""
    dest = (redirect or '').strip() or '/web'
    if not dest.startswith('/') or dest.startswith('//'):
        return '/web'
    return dest


def _session_user_is_logged_in():
    """True when the browser session belongs to a real (non-public) user."""
    uid = request.session.uid
    if not uid:
        return False
    user = request.env['res.users'].sudo().browse(uid)
    return bool(user.exists() and not user._is_public())


class AuctionRootRedirect(Website):
    """Override website's '/' route to redirect to the Odoo backend."""

    @http.route('/', type='http', auth='public', website=True, sitemap=False)
    def index(self, **kw):
        return request.redirect('/web', code=302)


class AuctionLoginController(Home):
    """Override the default Odoo web login to render our custom sporty theme."""

    @http.route('/web/login', type='http', auth='none', sitemap=False)
    def web_login(self, redirect=None, **kw):
        ensure_db()
        # Already signed in → skip the login form and go to the backend.
        if request.httprequest.method == 'GET' and _session_user_is_logged_in():
            return request.redirect(_safe_post_login_redirect(redirect))

        # Parent handles: CSRF, session auth, success redirect, error state
        response = super().web_login(redirect=redirect, **kw)
        # Only swap on GET / failed-POST — success returns a werkzeug redirect (no .template)
        if hasattr(response, 'template') and response.template == 'web.login':
            response.template = 'auction_login_theme.login'
            company = request.env['res.company'].sudo().search(
                [], order='id', limit=1)
            favicon_url = (
                '/web/image/res.company/%d/favicon' % company.id
                if company else '/web/static/img/favicon.ico'
            )
            response.qcontext['favicon_url'] = favicon_url
        return response


class AuctionLogoutController(Session):
    """Override logout to redirect with a ?logged_out=1 flag so the login page
    can display a goodbye animation before showing the sign-in form."""

    @http.route('/web/session/logout', type='http', auth='none')
    def logout(self, redirect='/web'):
        request.session.logout(keep_db=True)
        return request.redirect('/web/login?logged_out=1', 303)
