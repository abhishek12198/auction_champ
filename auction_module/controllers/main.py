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


import re
import logging
import werkzeug
import itertools
import pytz
import babel.dates
from collections import OrderedDict
import base64
import tempfile
import os
import subprocess
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from odoo import http, fields, api, SUPERUSER_ID
from odoo.api import call_kw
import odoo
from odoo.addons.http_routing.models.ir_http import slug, unslug
from odoo.addons.website.controllers.main import QueryURL
from odoo.addons.portal.controllers.portal import _build_url_w_params
from odoo.http import request
from odoo.osv import expression
from odoo.tools import html2plaintext
from odoo.tools.misc import get_lang
from odoo.tools import sql
from odoo.tools.image import image_process

_logger = logging.getLogger(__name__)


class Auction(http.Controller):

    def _resolve_tournament(self):
        """Return the tournament for the current request.

        Priority:
        1. The logged-in user's ``tournament_id`` field on their profile.
        2. The single tournament flagged ``active = True`` (legacy fallback).

        Routes with ``auth='none'`` that switch databases via ``_with_db``
        must NOT call this helper — they should keep their own active-based
        lookup because no user session is available in those contexts.
        """
        try:
            user_tournament = request.env.user.sudo().tournament_id
            if user_tournament:
                return user_tournament
        except Exception:
            pass
        return request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )

    def _tournament_auction_rules_ready(self, tournament):
        """True when the tournament has at least one auction.auction rule row."""
        if not tournament:
            return False
        if hasattr(tournament, 'has_auction_rules_ready'):
            return bool(tournament.has_auction_rules_ready())
        return bool(request.env['auction.auction'].sudo().search_count([
            ('tournament_id', '=', tournament.id),
        ]))

    def _auction_rules_required_page(self, tournament=None, db_name=None):
        """Themed lock screen: set auction rules before Console / Projector."""
        theme = 'vanilla'
        if tournament:
            theme = tournament.player_display_template or 'vanilla'
        company = request.env['res.company'].sudo().search([], limit=1)
        try:
            db = db_name or getattr(request.env.cr, 'dbname', None) or ''
        except Exception:
            db = db_name or ''
        try:
            html = request.render('auction_module.auction_rules_required', {
                'tournament': tournament,
                'theme': theme,
                'db_name': db,
                'res_company': company,
            }, lazy=False)
            response = request.make_response(
                html, [('Content-Type', 'text/html; charset=utf-8')]
            )
            response.status_code = 403
            return response
        except Exception:
            _logger.exception('Failed to render auction rules required page')
            name = (tournament.name if tournament else '') or 'this tournament'
            response = request.make_response(
                '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
                '<title>Set Auction Rules</title></head><body style="font-family:system-ui;padding:48px">'
                '<h2>Set Auction Rules first</h2>'
                '<p>Player Console and Projector stay locked for <strong>%s</strong> '
                'until auction rules are created.</p>'
                '<p><a href="/web">Back to AuctionChamp</a></p></body></html>' % name,
                [('Content-Type', 'text/html; charset=utf-8')],
            )
            response.status_code = 403
            return response

    @contextmanager
    def _with_db(self, db_name):
        """Open a cursor for *db_name* and inject it into the current request.

        Yields ``True`` on success or ``False`` if the database is unknown.
        The session cookie is never modified, so the same browser can access
        multiple databases without any 404/session conflict.

        Usage inside a route::

            with self._with_db(db_name) as ok:
                if not ok:
                    return self._not_found()
                # request.env now points at db_name
                html = request.render('module.template', ctx, lazy=False)
            return request.make_response(html, [('Content-Type', 'text/html')])
        """
        try:
            registry = odoo.registry(db_name)
        except Exception:
            yield False
            return

        with registry.cursor() as cr:
            # su=True is required: Environment(cr, SUPERUSER_ID, {}) alone
            # leaves env.su=False, so tournament-security mixins and ir.rule
            # still apply as if a normal admin user. Public auction pages
            # (Bid Summary, Players Left, …) must bypass those scopes.
            env = api.Environment(cr, SUPERUSER_ID, {}, True)
            # Save whatever the framework set (may be None for auth="none")
            old_cr, old_uid, old_env, old_context = (
                request._cr, request._uid, request._env, request._context
            )
            request._cr = cr
            request._uid = SUPERUSER_ID
            request._context = {}
            request._env = env
            try:
                yield True
            finally:
                # Restore so Odoo's own teardown doesn't double-close our cr
                request._cr = old_cr
                request._uid = old_uid
                request._env = old_env
                request._context = old_context

    def _resolve_db_for_slug(self, tournament_slug):
        """Return the database that actually contains *tournament_slug*.

        When several databases match the server's ``db_filter`` (or none can be
        inferred from the host), ``db_monodb`` returns ``None`` and blindly
        picking ``db_list()[0]`` sends the visitor to the wrong database, which
        then 404/500s because the slug does not exist there. Instead we probe
        each candidate database and return the first one whose
        ``auction.tournament`` has this slug. Falls back to the monodb / first
        database so single-db setups keep working unchanged.
        """
        from odoo.http import db_monodb, db_list
        mono = db_monodb(request.httprequest)
        candidates = []
        if mono:
            candidates.append(mono)
        try:
            for db in db_list(force=True, httprequest=request.httprequest):
                if db not in candidates:
                    candidates.append(db)
        except Exception:
            pass
        for db in candidates:
            try:
                registry = odoo.registry(db)
            except Exception:
                continue
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    if 'auction.tournament' not in env:
                        continue
                    match = env['auction.tournament'].sudo().search(
                        [('slug', '=', tournament_slug)], limit=1
                    )
                    if match:
                        return db
            except Exception:
                continue
        return mono or (candidates[0] if candidates else None)

    def _not_found(self):
        """Render the branded 404 page with a proper 404 HTTP status.
        Falls back to a plain werkzeug 404 when no DB context is available
        (e.g. called from an auth='none' route before _with_db succeeds).
        """
        if request._env is not None:
            try:
                response = request.render('auction_module.page_not_found', {})
                response.status_code = 404
                return response
            except Exception:
                pass
        # Fallback: plain HTML 404
        return request.make_response(
            '<html><head><title>404 Not Found</title></head><body><h1>404 Not Found</h1><p>The requested URL was not found on the server.</p></body></html>',
            status=404,
            headers=[('Content-Type', 'text/html; charset=utf-8')]
        )

    # ── Public Live Board access (tournament code gate) ─────────────────────

    @staticmethod
    def _normalize_tournament_code(code):
        """Normalize user input to AC#XXXXXXXXXXXX form when possible."""
        raw = re.sub(r'\s+', '', (code or '').strip().upper())
        if not raw:
            return ''
        if raw.startswith('AC#'):
            return raw
        if raw.startswith('AC') and len(raw) > 2 and raw[2:].replace('#', '').isdigit():
            digits = raw[2:].lstrip('#')
            return 'AC#%s' % digits
        if raw.isdigit():
            return 'AC#%s' % raw
        return raw

    def _live_board_session_key(self, tournament_id):
        return 'ac_live_board_unlocked_%s' % int(tournament_id)

    def _live_board_cookie_name(self, tournament_id):
        return 'ac_lb_%s' % int(tournament_id)

    def _live_board_cookie_token(self, tournament):
        """Stable device token derived from tournament code (no code stored in cookie)."""
        import hashlib
        secret = 'auctionchamp'
        try:
            secret = request.env['ir.config_parameter'].sudo().get_param(
                'database.secret', 'auctionchamp'
            ) or 'auctionchamp'
        except Exception:
            pass
        code = self._normalize_tournament_code(tournament.tournament_code or '')
        raw = '%s|%s|%s' % (tournament.id, code, secret)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]

    def _live_board_access_granted(self, tournament):
        """True when the board is open, or after a successful unlock (session/cookie)."""
        if not tournament:
            return False
        # Fresh DB read — avoid stale cache after organiser toggles protection
        try:
            tournament.invalidate_cache(['live_board_code_protected'])
        except Exception:
            pass
        protected = bool(
            tournament.sudo().read(['live_board_code_protected'])[0].get(
                'live_board_code_protected', True
            )
        )
        if not protected:
            return True
        key = self._live_board_session_key(tournament.id)
        if request.session.get(key):
            return True
        cookie = request.httprequest.cookies.get(self._live_board_cookie_name(tournament.id))
        expected = self._live_board_cookie_token(tournament)
        if cookie and expected and cookie == expected:
            # Restore session so subsequent requests in this browser stay unlocked
            request.session[key] = True
            return True
        return False

    def _live_board_grant_access(self, tournament, response=None):
        """Remember unlock for this browser (session + long-lived cookie)."""
        request.session[self._live_board_session_key(tournament.id)] = True
        # Ensure Odoo persists the session on auth='none' routes
        try:
            request.session.is_dirty = True
        except Exception:
            pass
        if response is not None and tournament.tournament_code:
            response.set_cookie(
                self._live_board_cookie_name(tournament.id),
                self._live_board_cookie_token(tournament),
                max_age=60 * 60 * 24 * 30,  # 30 days
                httponly=True,
                samesite='Lax',
                path='/',
            )
        return response

    def _live_board_try_unlock(self, tournament, submitted_code):
        """Validate code against tournament_code; grant session on success."""
        expected = self._normalize_tournament_code(tournament.tournament_code or '')
        given = self._normalize_tournament_code(submitted_code)
        if not expected:
            return False
        if given and expected == given:
            self._live_board_grant_access(tournament)
            return True
        return False

    def _live_board_unlock_redirect(self, db_name, tournament_slug, tournament):
        """Redirect to live board after unlock, attaching remember-cookie."""
        resp = werkzeug.utils.redirect(
            '/%s/%s/auction/live-board' % (db_name, tournament_slug),
            303,
        )
        return self._live_board_grant_access(tournament, response=resp)

    # ── Admin registration unlock (tournament code, once per browser) ─────────

    def _reg_admin_session_key(self, tournament_id):
        return 'ac_reg_admin_unlocked_%s' % int(tournament_id)

    def _reg_admin_cookie_name(self, tournament_id):
        return 'ac_reg_admin_%s' % int(tournament_id)

    def _reg_admin_cookie_token(self, tournament):
        """Device token for admin registration unlock (not the raw code)."""
        import hashlib
        secret = 'auctionchamp'
        try:
            secret = request.env['ir.config_parameter'].sudo().get_param(
                'database.secret', 'auctionchamp'
            ) or 'auctionchamp'
        except Exception:
            pass
        code = self._normalize_tournament_code(tournament.tournament_code or '')
        raw = 'reg-admin|%s|%s|%s' % (tournament.id, code, secret)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]

    def _reg_admin_unlocked(self, tournament):
        if not tournament:
            return False
        key = self._reg_admin_session_key(tournament.id)
        if request.session.get(key):
            return True
        cookie = request.httprequest.cookies.get(self._reg_admin_cookie_name(tournament.id))
        expected = self._reg_admin_cookie_token(tournament)
        if cookie and expected and cookie == expected:
            request.session[key] = True
            try:
                request.session.is_dirty = True
            except Exception:
                pass
            return True
        return False

    def _reg_admin_grant(self, tournament, response=None):
        request.session[self._reg_admin_session_key(tournament.id)] = True
        try:
            request.session.is_dirty = True
        except Exception:
            pass
        if response is not None and tournament.tournament_code:
            response.set_cookie(
                self._reg_admin_cookie_name(tournament.id),
                self._reg_admin_cookie_token(tournament),
                max_age=60 * 60 * 24 * 30,
                httponly=True,
                samesite='Lax',
                path='/',
            )
        return response

    def _reg_admin_try_unlock(self, tournament, submitted_code):
        expected = self._normalize_tournament_code(tournament.tournament_code or '')
        given = self._normalize_tournament_code(submitted_code)
        if not expected or not given or expected != given:
            return False
        self._reg_admin_grant(tournament)
        return True

    def _reg_path(self, db_name, tournament_slug, admin=False):
        base = '/%s/%s/player/register' % (db_name, tournament_slug)
        return base + '/admin' if admin else base

    def _reg_capacity(self, tournament):
        """Return max_reg, current draft count, slots_left, is_full."""
        max_reg = tournament.max_registrations or 0
        if hasattr(tournament, '_saas_effective_max_registrations'):
            max_reg = tournament._saas_effective_max_registrations()
        current_count = 0
        slots_left = None
        if max_reg > 0:
            current_count = request.env['auction.team.player'].sudo().search_count([
                ('tournament_id', '=', tournament.id),
                ('state', '=', 'draft'),
            ])
            slots_left = max(0, max_reg - current_count)
        is_full = bool(max_reg > 0 and current_count >= max_reg)
        return max_reg, current_count, slots_left, is_full

    def _reg_football_lookups(self, tournament):
        football_positions = request.env['auction.player.position'].sudo().browse()
        football_styles = request.env['auction.player.style'].sudo().browse()
        football_strengths = request.env['auction.player.strength'].sudo().browse()
        if tournament.tournament_type == 'football':
            football_positions = request.env['auction.player.position'].sudo().search(
                [('active', '=', True)], order='sequence asc, name asc')
            football_styles = request.env['auction.player.style'].sudo().search(
                [('active', '=', True)], order='sequence asc, name asc')
            football_strengths = request.env['auction.player.strength'].sudo().search(
                [('active', '=', True)], order='sequence asc, name asc')
        return football_positions, football_styles, football_strengths

    def _render_admin_register_unlock(self, tournament, db_name, tournament_slug,
                                      theme='vanilla', error=None, entered_code=''):
        html = request.render('auction_module.admin_registration_unlock_template', {
            'tournament': tournament,
            'theme': theme,
            'db_name': db_name,
            'tournament_slug': tournament_slug,
            'error': error,
            'entered_code': entered_code or '',
        }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    def _render_live_board_unlock(self, tournament, db_name, tournament_slug,
                                  theme='vanilla', error=None, entered_code=''):
        html = request.render('auction_module.live_board_unlock_template', {
            'tournament': tournament,
            'theme': theme,
            'db_name': db_name,
            'tournament_slug': tournament_slug,
            'error': error,
            'entered_code': entered_code or '',
        }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route(['/auction/player_selector', '/auction/player_selector/'],
                type='http', auth="none", website=False, sitemap=False)
    def player_selector_legacy(self, **kw):
        """Redirect legacy URL to db+slug prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            dbs = db_list(force=True, httprequest=request.httprequest)
            db_name = dbs[0] if dbs else None
        if not db_name:
            return self._not_found()
        # Prefer ?t=slug; otherwise resolve via _resolve_tournament (SaaS-aware).
        t_slug = (kw.get('t') or '').strip()
        if not t_slug:
            try:
                with self._with_db(db_name) as ok:
                    if ok:
                        tournament = self._resolve_tournament()
                        t_slug = tournament.slug if tournament else ''
            except Exception:
                t_slug = ''
        target = '/{}/auction/player_selector/{}'.format(
            db_name, t_slug + '/' if t_slug else '')
        return werkzeug.utils.redirect(target, 302)

    @http.route([
        '/<string:db_name>/auction/player_selector/',
        '/<string:db_name>/auction/player_selector/<string:tournament_slug>/',
    ], type='http', auth="none", website=False, sitemap=False)
    def player_selector(self, db_name, tournament_slug=None, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            if tournament_slug:
                tournament = request.env['auction.tournament'].sudo().search(
                    [('slug', '=', tournament_slug)], limit=1)
            else:
                # Use resolver (SaaS working tournament) — not "first active".
                tournament = self._resolve_tournament()
            if tournament and not self._tournament_auction_rules_ready(tournament):
                return self._auction_rules_required_page(tournament, db_name=db_name)
            # Resume auction view on the projector (dismiss leftover pool/fixture board)
            if tournament:
                tournament.action_dismiss_projector_board()
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
            Tier = request.env['auction.player.tier'].sudo()
            tiers = Tier.search(
                [('tournament_id', '=', tournament.id)], order='name asc',
            ) if tournament else Tier.browse()
            company = request.env['res.company'].sudo().search([], limit=1)
            html = request.render('auction_module.player_sequence_selector', {
                'tournament': tournament,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug or (tournament.slug if tournament else ''),
                'tiers': tiers,
                'res_company': company,
            }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    #sequence_template_part
    @http.route('/auction/get_players_queue', type='json', auth='public', website=True)
    def get_players_queue(self, tournament_id=None):
        return self._players_queue_payload(tournament_id)

    @http.route('/<string:db_name>/auction/get_players_queue',
                type='json', auth='none', website=False, csrf=False)
    def get_players_queue_db(self, db_name, tournament_id=None):
        """Database-explicit grid so the operator selects players (and IDs)
        from the same database the projector reads from."""
        with self._with_db(db_name) as ok:
            if not ok:
                return []
            return self._players_queue_payload(tournament_id)

    def _players_queue_payload(self, tournament_id=None):
        if tournament_id:
            tournament = request.env['auction.tournament'].sudo().browse(int(tournament_id))
        else:
            tournament = self._resolve_tournament()
        domain = [('icon_player', '=', False), ('state', '!=', 'draft')]
        if tournament:
            domain.append(('tournament_id', '=', tournament.id))
        players = request.env['auction.team.player'].sudo().search(domain, order='sl_no asc')

        # Build a map of player_id -> sold points from auction.auction.player
        sold_player_ids = [p.id for p in players if p.state == 'sold']
        points_map = {}
        if sold_player_ids:
            lines = request.env['auction.auction.player'].sudo().search(
                [('player_id', 'in', sold_player_ids)])
            for line in lines:
                points_map[line.player_id.id] = line.points

        return [
            {
                'serial': p.sl_no,
                'id': p.id,
                'name': p.name or '',
                'role': p.role or '',
                'tier_id': p.tier_id.id if p.tier_id else False,
                'tier_color': p.tier_color or '',
                'tier_name': p.tier_id.name if p.tier_id else '',
                'is_mystery': bool(p.tier_id and p.tier_id.mystery),
                'mystery_revealed': bool(p.mystery_revealed),
                'state': p.state,
                'team_name': p.assigned_team_id.name if p.state == 'sold' and p.assigned_team_id else '',
                'team_logo': p.assigned_team_id.logo.decode('utf-8') if p.state == 'sold' and p.assigned_team_id and p.assigned_team_id.logo else '',
                'sold_points': points_map.get(p.id, 0) if p.state == 'sold' else 0,
            }
            for p in players
        ]

    def _reopen_pool_payload(self, tournament_id=None, db_name=None):
        """Draft + Unsold players available to reopen into the manual auction grid."""
        if tournament_id:
            tournament = request.env['auction.tournament'].sudo().browse(int(tournament_id))
        else:
            tournament = self._resolve_tournament()
        if not tournament or not tournament.exists():
            return {'draft': [], 'unsold': [], 'draft_count': 0, 'unsold_count': 0}
        Player = request.env['auction.team.player'].sudo().with_context(active_test=False)
        t_domain = [('tournament_id', '=', tournament.id), ('icon_player', '=', False)]
        draft_players = Player.search(
            t_domain + [('state', '=', 'draft')], order='sl_no asc, name asc')
        unsold_players = Player.search(
            t_domain + [('state', '=', 'unsold')], order='sl_no asc, name asc')
        db = db_name or ''

        def _row(p):
            role = p.role or ''
            if tournament.tournament_type == 'football' and p.dominant_position_id:
                role = p.dominant_position_id.name or role
            photo_url = ''
            if p.photo and db:
                photo_url = '/%s/auction/public/image/auction.team.player/%d/photo' % (db, p.id)
            return {
                'id': p.id,
                'serial': p.sl_no or 0,
                'name': p.name or '',
                'role': role,
                'tier_id': p.tier_id.id if p.tier_id else False,
                'tier_name': p.tier_id.name if p.tier_id else '',
                'tier_color': p.tier_id.color if p.tier_id else '',
                'photo_url': photo_url,
                'state': p.state,
            }

        return {
            'draft': [_row(p) for p in draft_players],
            'unsold': [_row(p) for p in unsold_players],
            'draft_count': len(draft_players),
            'unsold_count': len(unsold_players),
        }

    @http.route('/auction/get_reopen_pool', type='json', auth='public', website=True)
    def get_reopen_pool(self, tournament_id=None):
        return self._reopen_pool_payload(tournament_id)

    @http.route('/<string:db_name>/auction/get_reopen_pool',
                type='json', auth='none', website=False, csrf=False)
    def get_reopen_pool_db(self, db_name, tournament_id=None):
        with self._with_db(db_name) as ok:
            if not ok:
                return {'draft': [], 'unsold': [], 'draft_count': 0, 'unsold_count': 0}
            return self._reopen_pool_payload(tournament_id, db_name=db_name)

    @http.route('/auction/get_player_data', type='json', auth='public', website=True)
    def get_player_data(self, player_id):
        """Fetch full player data for modal display"""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))

        if not player.exists():
            return {}

        # Convert photo to base64 if exists
        photo_base64 = ""
        if player.photo:
            photo_base64 = player.photo.decode('utf-8') if isinstance(player.photo, bytes) else player.photo

        return {
            'id': player.id,
            'sl_no': player.sl_no,
            'name': player.name,
            'role': player.role or 'N/A',
            'batting_style': player.batting_style or 'N/A',
            'bowling_style': player.bowling_style or 'N/A',
            'contact': player.contact or 'N/A',
            'blood_group': player.blood_group or 'N/A',
            'address': player.address or 'N/A',
            'photo': photo_base64,
            'tournament_id': player.tournament_id.id if player.tournament_id else None,
            'tournament_name': player.tournament_id.name if player.tournament_id else '',
            **_football_display_payload(player),
        }

    @http.route('/auction/player_card/<int:player_id>', type='http', auth='public', website=True)
    def get_player_card(self, player_id):
        """Render the full themed player card page for iframe embedding in the selector drawer."""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return request.not_found()

        tournament = self._resolve_tournament()
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        auction_ids = request.env['auction.auction'].sudo().search(
            [('tournament_id', '=', tournament.id)] if tournament else [])

        template_map = {
            'vanilla':      'auction_module.player_template_new',
            'butterscotch': 'auction_module.player_template_butterscotch',
            'strawberry':   'auction_module.player_template_strawberry',
            'cherry':       'auction_module.player_template_cherry',
            'pistah':       'auction_module.player_template_pistah',
            'lemon':        'auction_module.player_template_lemon',
            'blackberry':   'auction_module.player_template_blackberry',
        }
        template_ref = template_map.get(theme, 'auction_module.player_template_new')
        if tournament and tournament.tournament_type == 'football':
            template_ref = 'auction_module.player_template_football'
        return request.render(template_ref, {
            'player':      player,
            'tournament':  tournament,
            'auction_ids': auction_ids,
        })

    @http.route('/auction/player_modal/<int:player_id>', type='http', auth='public', website=True)
    def get_player_modal(self, player_id):
        """Render themed player card for the sequence-selector drawer."""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return request.make_response('{"error": "Player not found"}',
                                         headers=[('Content-Type', 'application/json')])

        tournament = self._resolve_tournament()

        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        _unsold_color = {
            'cherry':       '#DC143C',
            'butterscotch': '#F5C842',
            'strawberry':   '#C2185B',
            'pistah':       '#6BBF4E',
            'lemon':        '#E8C200',
            'blackberry':   '#3B82F6',
        }.get(theme, '#b71c1c')

        _unsold_text = '#090912' if theme in ('butterscotch', 'lemon') else '#fff'

        sold_points = 0
        if player.state == 'sold':
            auction_line = request.env['auction.auction.player'].sudo().search(
                [('player_id', '=', player.id)], limit=1)
            sold_points = auction_line.points if auction_line else 0

        html_content = request.env['ir.ui.view']._render_template(
            'auction_module.player_template_modal_content', {
                'player':               player,
                'tournament':           tournament,
                'theme':                theme,
                'unsold_color':         _unsold_color,
                'unsold_text_color':    _unsold_text,
                'sold_display_seconds': tournament.sold_display_seconds if tournament else 5,
                'sold_points':          sold_points,
            })

        return request.make_response(html_content,
                                     headers=[('Content-Type', 'text/html; charset=utf-8')])

    # Model/method pairs the operator console is allowed to invoke through the
    # database-explicit dispatcher below. Keep this tight — the endpoint is
    # auth="none", so only these whitelisted calls may run.
    _CONSOLE_CALL_WHITELIST = {
        'auction.team.player': {
            'action_unsold', 'action_auction', 'action_clear_stage',
            'action_set_on_stage', 'get_sell_teams_data', 'action_sell_from_web',
            'action_reveal_mystery',
        },
        'auction.tournament': {'set_dice_state', 'action_toggle_break_time', 'action_set_break_time'},
        'auction.auction': {'search_read'},
    }

    @http.route('/<string:db_name>/auction/console_call',
                type='json', auth='none', website=False, csrf=False)
    def console_call(self, db_name, model=None, method=None, args=None, kwargs=None):
        """Database-explicit, whitelisted replacement for /web/dataset/call_kw.

        The operator console (player_selector) is served from a ``/<db>/...``
        URL via ``_with_db``, which never binds the session to that database.
        Its mutating actions (sell / unsold / bring-back / dice) previously went
        through ``/web/dataset/call_kw``, which uses the session database. On a
        server whose ``db_filter`` matches several databases, that could execute
        the sale in the wrong database and never reach the projector. Routing
        through the db in the URL guarantees every console action runs against
        the same database the page and projector use.
        """
        allowed = self._CONSOLE_CALL_WHITELIST.get(model)
        if not allowed or method not in allowed:
            return {'error': 'method not allowed'}
        with self._with_db(db_name) as ok:
            if not ok:
                return {'error': 'unknown database'}
            recordset = request.env[model].sudo()
            return call_kw(recordset, method, args or [], kwargs or {})

    @http.route('/auction/player_quick_data/<int:player_id>', type='json', auth='public', website=True)
    def player_quick_data(self, player_id):
        """Single-call endpoint: return all drawer data AND set player on stage atomically.

        Replaces the 2-4 separate callKw round-trips previously used by the player_selector
        JS (read player + read team logo + read sold points + action_set_on_stage) with a
        single HTTP call, dramatically reducing latency especially in production.
        """
        return self._player_quick_data_payload(player_id)

    @http.route('/<string:db_name>/auction/player_quick_data/<int:player_id>',
                type='json', auth='none', website=False, csrf=False)
    def player_quick_data_db(self, db_name, player_id):
        """Database-explicit variant of :meth:`player_quick_data`.

        The operator console is served from a ``/<db>/...`` URL via ``_with_db``,
        which never binds the session to that database. On servers where the
        ``db_filter`` matches several databases, the non-prefixed route above
        resolves to the wrong (session) database, so the player is set on stage
        somewhere the projector never polls. Routing through the db in the path
        guarantees the on-stage write lands in the same database the projector
        reads from.
        """
        with self._with_db(db_name) as ok:
            if not ok:
                return {'error': 'not found'}
            return self._player_quick_data_payload(player_id)

    def _player_quick_data_payload(self, player_id):
        player = request.env['auction.team.player'].sudo().browse(player_id)
        if not player.exists():
            return {'error': 'not found'}

        # Set on stage in the same DB transaction — projector sees the update immediately
        try:
            player.action_set_on_stage()
        except Exception as exc:
            _logger.exception(
                'action_set_on_stage failed for player %s', player_id
            )
            return {
                'error': 'stage_failed',
                'message': str(exc) or 'Could not put player on stage',
            }

        photo = ''
        if player.photo:
            photo = player.photo.decode('utf-8') if isinstance(player.photo, bytes) else player.photo

        result = {
            'id': player.id,
            'sl_no': player.sl_no,
            'name': player.name or '',
            'role': player.role or '',
            'batting_style': player.batting_style or '',
            'bowling_style': player.bowling_style or '',
            'contact': player.contact or '',
            'masked_contact': player.masked_contact or '',
            'photo': photo,
            'state': player.state or '',
            'tier_id': [player.tier_id.id, player.tier_id.name] if player.tier_id else False,
            'tier_color': player.tier_color or '',
            'assigned_team_id': [player.assigned_team_id.id, player.assigned_team_id.name] if player.assigned_team_id else False,
            'team_logo': '',
            'team_name': '',
            'sold_points': 0,
            'base_price': int(player.effective_base_price or player.base_price or 0),
            'icon_player': bool(player.icon_player),
            'is_mystery': bool(player.tier_id and player.tier_id.mystery),
            'mystery_revealed': bool(player.mystery_revealed),
        }

        if player.state == 'sold' and player.assigned_team_id:
            result['team_name'] = player.assigned_team_id.name or ''
            if player.assigned_team_id.logo:
                logo = player.assigned_team_id.logo
                result['team_logo'] = logo.decode('utf-8') if isinstance(logo, bytes) else logo
            auction_line = request.env['auction.auction.player'].sudo().search(
                [('player_id', '=', player_id)], limit=1)
            result['sold_points'] = auction_line.points if auction_line else 0

        result.update(_football_display_payload(player))

        # Redact identity for unrevealed mystery players (drawer / projector sync)
        if result['is_mystery'] and not result['mystery_revealed']:
            result.update({
                'name': 'Mystery Player',
                'role': '???',
                'sl_no': 0,
                'photo': '',
                'batting_style': '',
                'bowling_style': '',
                'contact': '',
                'masked_contact': '',
                'icon_player': False,
                'dominant_position': '???',
                'preferred_foot': '',
                'secondary_positions': '',
                'age': '',
                'height': '',
                'weight': '',
                'work_rate': '',
                'p_category': '',
                'blood_group': '',
                'mobile': '',
                'location': '',
                'use_other_attributes': False,
                'other_attributes': [],
                'playing_styles': [],
                'strengths': [],
            })
            # Keep tier name hidden while locked (base price stays)
            if result.get('tier_id'):
                result['tier_id'] = [result['tier_id'][0], 'Mystery']
        return result

    @http.route('/<string:db_name>/auction/player_clear_stage/<int:player_id>',
                type='json', auth='none', website=False, csrf=False)
    def player_clear_stage_db(self, db_name, player_id):
        """Database-explicit clear-stage so the projector returns to waiting."""
        with self._with_db(db_name) as ok:
            if not ok:
                return {'error': 'not found'}
            player = request.env['auction.team.player'].sudo().browse(player_id)
            if not player.exists():
                return {'error': 'not found'}
            try:
                player.action_clear_stage()
            except Exception:
                _logger.exception(
                    'action_clear_stage failed for player %s', player_id
                )
                # Last resort: clear stage flag so projector can return to waiting
                try:
                    player.sudo().with_context(saas_skip_freeze=True).write(
                        {'is_on_stage': False}
                    )
                except Exception:
                    pass
            return {'success': True}

    @http.route('/auction/player_correction_teams/<int:player_id>', type='json', auth='user', website=True)
    def player_correction_teams(self, player_id):
        """Fast single-call replacement for get_all_teams_for_correction via callKw."""
        player = request.env['auction.team.player'].sudo().browse(player_id)
        if not player.exists():
            return []
        return player.get_all_teams_for_correction()

    @http.route('/auction/player_update_sale', type='json', auth='user', website=True)
    def player_update_sale(self, player_id, new_points, new_team_id):
        """Fast single-call replacement for action_update_sale via callKw."""
        player = request.env['auction.team.player'].browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'Player not found'}
        return player.action_update_sale(int(new_points), int(new_team_id))

    # @http.route('/auction/get_players_queue', type='http', auth='public', website=True)
    # def get_players_queue(self):
    #
    #     players = request.env['auction.team.player'].sudo().get_auction_players(
    #     )
    #
    #     result = [
    #         {'serial': p.serial_number}
    #         for p in players
    #     ]
    #
    #     return json.dumps(result)
    #history part
    @http.route('/live_updates', type='http', auth='public', website=True)
    def live_updates_page(self):
        tournament_id = self._resolve_tournament()
        return request.render('auction_module.live_updates_template', {'tournament': tournament_id})

    @http.route('/get_live_updates', type='json', auth='public')
    def get_live_updates(self):
        records = request.env['auction.history'].sudo().search([], order='create_date desc', limit=100)
        return [
            {
                'message': rec.message,
                'timestamp': rec.create_date.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %I:%M:%S %p'),
                'avatar_base64':rec.player_photo,
                'avatar_team':  rec.team_id and rec.team_id.logo or False,
                # 'author': rec.author
            }
            for rec in records
        ]

    @http.route(['''/auction/show/team/balance1'''], type='http', auth="public", website=True, sitemap=True)
    def auction_team_balance_test(self, **kwargs):
        auctions = request.env['auction.auction'].sudo().search([])
        tournament = auctions.mapped('tournament_id')
        # result = request.render("auction_module.auction_details_show", {'teams': auctions, 'tournament': tournament})
        data = json.dumps({'team_name': 'KCB Machismo', 'balance': 1000})
        headers = [('Content-Type', 'application/json'),
                   ('Cache-Control', 'no-store')]
        return request.make_response(data, headers)



    @http.route(['''/auction/show/team/balance'''], type='http', auth="none", website=False)
    def auction_team_balance_legacy(self, **kwargs):
        """Redirect legacy /auction/show/team/balance URL to the db-slug-based URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
            if tournament and tournament.slug:
                return werkzeug.utils.redirect('/{}/{}/auction/show/team/balance'.format(db_name, tournament.slug), 301)
        return self._not_found()

    @http.route(['''/<string:tournament_slug>/auction/show/team/balance'''], type='http', auth="none", website=False)
    def auction_team_balance_slug_legacy(self, tournament_slug, **kwargs):
        """Redirect old slug-only URL to db-prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        return werkzeug.utils.redirect('/{}/{}/auction/show/team/balance'.format(db_name, tournament_slug), 301)

    def _balance_auction_records(self, tournament):
        """Auctions for Bid Summary — ignore tournament-security scopes.

        Also match via team.tournament_id so rows still appear when
        ``auction.auction.tournament_id`` was left empty (common SaaS
        edge case after rules were set from a team list).
        """
        Auction = request.env['auction.auction'].sudo().with_context(
            auction_skip_tournament_security=True,
            active_test=True,
        )
        return Auction.search([
            '|',
            ('tournament_id', '=', tournament.id),
            ('team_id.tournament_id', '=', tournament.id),
        ])

    def _render_team_balance(self, db_name, tournament, tournament_slug, **kwargs):
        """Shared Bid Summary renderer (HTML)."""
        auctions = self._balance_auction_records(tournament)
        # Prefetch relations used by the balance page / max_call compute so
        # QWeb does not trigger per-team SQL while rendering list+grid+mobile.
        auctions.mapped('team_id')
        auctions.mapped('player_ids.tier_id')
        auctions.mapped('tier_limit_ids.tier_id')
        auctions.mapped('auction_bid_slab_ids')
        # Force max_call under the sudo/skip-security env before QWeb.
        for auction in auctions:
            auction.max_call
        theme = tournament.player_display_template or 'vanilla'
        access_type = 'internal' if request.session.uid else 'public'
        balance_template_map = {
            'pistah': 'auction_module.auction_details_show_pistah',
            'blackberry': 'auction_module.auction_details_show_blackberry',
        }
        template_ref = balance_template_map.get(theme, 'auction_module.auction_details_show')
        q = request.httprequest.args
        from_projector = (kwargs.get('from') or q.get('from') or '') == 'projector'
        mode = kwargs.get('mode') or q.get('mode') or (
            'light' if theme in ('lemon', 'strawberry') else 'dark')
        if mode not in ('dark', 'light'):
            mode = 'dark'
        company = request.env['res.company'].sudo().search([], limit=1)
        slug = tournament_slug or tournament.slug or ''
        return request.render(template_ref, {
            'teams': auctions,
            'tournament': tournament,
            'type': access_type,
            'theme': theme,
            'db_name': db_name,
            'tournament_slug': slug,
            'from_projector': from_projector,
            'mode': mode,
            'res_company': company,
        }, lazy=False)

    @http.route(['''/<string:db_name>/<string:tournament_slug>/auction/show/team/balance'''], type='http', auth="none", website=False)
    def auction_team_balance(self, db_name, tournament_slug, **kwargs):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            Tournament = request.env['auction.tournament'].sudo().with_context(
                auction_skip_tournament_security=True,
            )
            tournament = Tournament.search([('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return self._not_found()
            try:
                html = self._render_team_balance(
                    db_name, tournament, tournament_slug, **kwargs
                )
            except Exception:
                _logger.exception(
                    'Bid Summary render failed db=%s slug=%s', db_name, tournament_slug
                )
                return request.make_response(
                    '<!DOCTYPE html><html><body style="font-family:system-ui;padding:24px">'
                    '<h2>Bid Summary unavailable</h2>'
                    '<p>Could not render the bid summary for this tournament. '
                    'Confirm auction rules are set, then refresh.</p>'
                    '</body></html>',
                    [
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Cache-Control', 'private, max-age=0, must-revalidate'),
                    ],
                    status=500,
                )
        return request.make_response(html, [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'private, max-age=0, must-revalidate'),
            ('X-Frame-Options', 'SAMEORIGIN'),
        ])

    @http.route(['''/auction/show/team/balance/json'''], type='http', auth="none", website=False)
    def auction_team_balance_json_legacy(self, **kwargs):
        """Redirect legacy /auction/show/team/balance/json URL to the db-slug-based URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
            if tournament and tournament.slug:
                return werkzeug.utils.redirect('/{}/{}/auction/show/team/balance/json'.format(db_name, tournament.slug), 301)
        return self._not_found()

    @http.route(['''/<string:tournament_slug>/auction/show/team/balance/json'''], type='http', auth="none", website=False)
    def auction_team_balance_json_slug_legacy(self, tournament_slug, **kwargs):
        """Redirect old slug-only URL to db-prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        return werkzeug.utils.redirect('/{}/{}/auction/show/team/balance/json'.format(db_name, tournament_slug), 301)

    @http.route(['''/<string:db_name>/<string:tournament_slug>/auction/show/team/balance/json'''], type='http', auth="none", website=False)
    def auction_team_balance_json(self, db_name, tournament_slug, **kwargs):
        with self._with_db(db_name) as ok:
            if not ok:
                return request.make_response(
                    json.dumps({'error': 'unknown database'}),
                    headers=[('Content-Type', 'application/json')]
                )
            Tournament = request.env['auction.tournament'].sudo().with_context(
                auction_skip_tournament_security=True,
            )
            tournament = Tournament.search([('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return request.make_response(
                    json.dumps({'error': 'tournament not found'}),
                    headers=[('Content-Type', 'application/json')]
                )
            auctions = self._balance_auction_records(tournament)
            auctions.mapped('player_ids.tier_id')
            auctions.mapped('tier_limit_ids.tier_id')
            auctions.mapped('auction_bid_slab_ids')
            Player = request.env['auction.team.player'].sudo().with_context(
                auction_skip_tournament_security=True,
            )
            on_stage = Player.search(
                [('tournament_id', '=', tournament.id), ('is_on_stage', '=', True)], limit=1
            )
            player_on_stage = on_stage if on_stage else None
            teams_data = []
            for auction in auctions:
                teams_data.append({
                    'id': auction.id,
                    'remaining_players_count': auction.remaining_players_count,
                    'remaining_points': auction.remaining_points,
                    'max_call': auction.get_max_bid_for_team(auction, player_on_stage),
                })
            data = json.dumps({'teams': teams_data})
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'max-age=3')]
        return request.make_response(data, headers)

    def _tournament_all_squads_full(self, tournament):
        """True when every team in the tournament has a full squad (no slots left)."""
        if not tournament:
            return False
        auctions = request.env['auction.auction'].sudo().search([
            ('tournament_id', '=', tournament.id),
        ])
        if not auctions:
            return False
        return all((auc.remaining_players_count or 0) <= 0 for auc in auctions)

    def _render_auction_resume(self, tournament, db_name, theme, auction_ids,
                               draft_players, unsold_players, auction_players,
                               draft_count, unsold_count, sold_count, auction_count,
                               tiers, squads_full=False):
        return request.render('auction_module.auction_resume_template', {
            'tournament': tournament,
            'theme': theme,
            'db_name': db_name,
            'draft_players': draft_players,
            'unsold_players': unsold_players,
            'auction_players': auction_players,
            'draft_count': draft_count,
            'unsold_count': unsold_count,
            'sold_count': sold_count,
            'auction_count': auction_count,
            'auction_ids': auction_ids,
            'tiers': tiers,
            'squads_full': bool(squads_full),
        }, lazy=False)

    def _resume_mark_auction_unsold(self, tournament):
        """Mark all remaining In-Auction players as unsold (squads-full exit path)."""
        Player = request.env['auction.team.player'].sudo()
        players = Player.search([
            ('tournament_id', '=', tournament.id),
            ('state', '=', 'auction'),
            ('icon_player', '=', False),
        ])
        if not players:
            return players
        for player in players:
            player.write({'state': 'unsold', 'is_on_stage': False})
            message = (player.name or 'Player') + ' is Unsold!'
            player.create_unsold_auction_history(
                message,
                tournament_id=tournament.id,
                player=player,
            )
        tournament.sudo().write({
            'stamp_player_id': False,
            'stamp_state': False,
            'stamp_expires_at': False,
        })
        return players

    @http.route(['''/auction/display_auction/'''], type='http', auth="none", website=False, sitemap=False)
    def display_auction_legacy(self, **kwargs):
        """Redirect legacy URL to db-prefixed URL, preserving ?t= tournament slug."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        slug = kwargs.get('t', '')
        target = '/{}/auction/display_auction/{}'.format(db_name, slug + '/' if slug else '')
        return werkzeug.utils.redirect(target, 301)

    @http.route([
        '''/<string:db_name>/auction/display_auction/''',
        '''/<string:db_name>/auction/display_auction/<string:tournament_slug>/''',
    ], type='http', auth="none", website=False, sitemap=False)
    def display_auction(self, db_name, tournament_slug=None, **kwargs):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            # Resolve tournament: prefer slug in URL, fall back to active flag (legacy)
            if tournament_slug:
                tournament_id = request.env['auction.tournament'].sudo().search(
                    [('slug', '=', tournament_slug)], limit=1
                )
            else:
                tournament_id = request.env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1
                )
            if tournament_id and not self._tournament_auction_rules_ready(tournament_id):
                return self._auction_rules_required_page(tournament_id, db_name=db_name)
            exclude_id = kwargs.get('exclude', 0)
            preview = str(kwargs.get('preview', '') or '') in ('1', 'true', 'True')
            # Opening Player Showcase / display_auction must take the projector
            # back to the live player — do not leave a prior pool/fixture board up.
            # Skip for preview=1 prefetch so we do not flicker the board mid-countdown.
            if tournament_id and not preview:
                tournament_id.action_dismiss_projector_board()

            auction_ids = request.env['auction.auction'].sudo().search(
                [('tournament_id', '=', tournament_id.id)] if tournament_id else []
            )
            all_squads_full = self._tournament_all_squads_full(tournament_id)
            PlayerActive = request.env['auction.team.player'].sudo()
            t_domain_active = (
                [('tournament_id', '=', tournament_id.id)] if tournament_id else [('id', '=', False)]
            )
            auction_queue_count = PlayerActive.search_count(
                t_domain_active + [('state', '=', 'auction'), ('icon_player', '=', False)]
            )

            # All squads full but players still In Auction → resume screen with
            # bulk-unsold action (do not keep presenting unbuyable players).
            if tournament_id and all_squads_full and auction_queue_count > 0:
                theme = tournament_id.player_display_template or 'vanilla'
                Player = PlayerActive.with_context(active_test=False)
                t_domain = [('tournament_id', '=', tournament_id.id)]
                sold_count = Player.search_count(t_domain + [('state', '=', 'sold')])
                draft_count = Player.search_count(t_domain + [('state', '=', 'draft')])
                unsold_count = Player.search_count(t_domain + [('state', '=', 'unsold')])
                draft_players = Player.search(
                    t_domain + [('state', '=', 'draft')],
                    order='sl_no asc, name asc',
                )
                unsold_players = Player.search(
                    t_domain + [('state', '=', 'unsold')],
                    order='sl_no asc, name asc',
                )
                auction_players = PlayerActive.search(
                    t_domain + [('state', '=', 'auction'), ('icon_player', '=', False)],
                    order='sl_no asc, name asc',
                )
                Tier = request.env['auction.player.tier'].sudo()
                tiers = Tier.search(
                    [('tournament_id', '=', tournament_id.id)],
                    order='name asc',
                )
                if not tiers:
                    tiers = (draft_players | unsold_players | auction_players).mapped('tier_id')
                html = self._render_auction_resume(
                    tournament_id, db_name, theme, auction_ids,
                    draft_players, unsold_players, auction_players,
                    draft_count, unsold_count, sold_count, len(auction_players),
                    tiers, squads_full=True,
                )
                return request.make_response(
                    html, [('Content-Type', 'text/html; charset=utf-8')]
                )

            # If no explicit "next player" request, resume the player already on stage
            if not exclude_id:
                on_stage_domain = [('is_on_stage', '=', True), ('state', '=', 'auction')]
                if tournament_id:
                    on_stage_domain.append(('tournament_id', '=', tournament_id.id))
                player = request.env['auction.team.player'].sudo().search(on_stage_domain, limit=1)
            else:
                player = None

            # No on-stage player (or caller wants next) → pick one.
            # preview=1 (prefetch during countdown) must not flip is_on_stage
            # so the projector keeps showing the current player until commit.
            if not player:
                player = request.env['auction.team.player'].sudo().get_random_player(
                    exclude_id=exclude_id,
                    tournament_id=tournament_id,
                    commit_stage=not preview,
                )
            if player:
                template_map = {
                    'vanilla':       'auction_module.player_template_new',
                    'butterscotch':  'auction_module.player_template_butterscotch',
                    'strawberry':    'auction_module.player_template_strawberry',
                    'cherry':        'auction_module.player_template_cherry',
                    'pistah':        'auction_module.player_template_pistah',
                    'blackberry':    'auction_module.player_template_blackberry',
                    'lemon':         'auction_module.player_template_lemon',
                }
                chosen = tournament_id.player_display_template if tournament_id else 'vanilla'
                template_ref = template_map.get(chosen, 'auction_module.player_template_new')
                # Always use the themed presentation (Sold / Unsold / Next Player).
                # Football attributes are already rendered inside those themes —
                # do not swap to player_template_football (card-only, no controls).
                html = request.render(template_ref, {
                    'player': player,
                    'tournament': tournament_id,
                    'auction_ids': auction_ids,
                    'db_name': db_name,
                    'res_company': request.env['res.company'].sudo().search([], limit=1),
                }, lazy=False)
            else:
                theme = tournament_id.player_display_template if tournament_id else 'vanilla'
                t_domain = [('tournament_id', '=', tournament_id.id)] if tournament_id else [('id', '=', False)]
                # active_test=False so archived players still count for routing decisions
                Player = request.env['auction.team.player'].sudo().with_context(active_test=False)
                sold_count = Player.search_count(t_domain + [('state', '=', 'sold')])
                draft_count = Player.search_count(t_domain + [('state', '=', 'draft')])
                unsold_count = Player.search_count(t_domain + [('state', '=', 'unsold')])
                declared_done = bool(tournament_id and tournament_id.auction_declared_complete)

                def _thank_you_html():
                    teams_payload = []
                    for auc in auction_ids:
                        team = auc.team_id
                        logo_url = ''
                        if team and team.logo and db_name:
                            logo_url = '/%s/auction/public/image/auction.team/%d/logo' % (db_name, team.id)
                        players_payload = []
                        for line in auc.player_ids:
                            p = line.player_id
                            if not p:
                                continue
                            photo_url = ''
                            if p.photo and db_name:
                                photo_url = '/%s/auction/public/image/auction.team.player/%d/photo' % (db_name, p.id)
                            role = p.role or ''
                            if tournament_id and tournament_id.tournament_type == 'football' and p.dominant_position_id:
                                role = p.dominant_position_id.name or role
                            players_payload.append({
                                'name': p.name or '',
                                'role': role,
                                'points': line.points or 0,
                                'photo_url': photo_url,
                                'tier': p.tier_id.name if p.tier_id else '',
                                'icon': bool(p.icon_player),
                            })
                        teams_payload.append({
                            'id': auc.id,
                            'name': team.name if team else 'Team',
                            'logo_url': logo_url,
                            'manager': (team.manager if team else '') or '',
                            'player_count': len(players_payload),
                            'spent': (auc.total_point or 0) - (auc.remaining_points or 0),
                            'remaining': auc.remaining_points or 0,
                            'total_point': auc.total_point or 0,
                            'players': players_payload,
                        })
                    return request.render("auction_module.thank_you_template", {
                        'tournament': tournament_id,
                        'theme': theme,
                        'auction_ids': auction_ids,
                        'sold_count': sold_count,
                        'draft_count': draft_count,
                        'unsold_count': unsold_count,
                        'db_name': db_name,
                        'teams_payload': teams_payload,
                        'teams_json': json.dumps(teams_payload),
                        'can_reopen': bool(draft_count or unsold_count),
                    }, lazy=False)

                # Routing (In-Auction queue empty):
                # - Declared complete → Thank You
                # - Any Draft or Unsold left → Resume (operator can open them)
                # - Sold only (nothing left to open) → Thank You
                # - No players at all → Welcome
                if declared_done:
                    html = _thank_you_html()
                elif draft_count > 0 or unsold_count > 0:
                    draft_players = Player.search(
                        t_domain + [('state', '=', 'draft')],
                        order='sl_no asc, name asc',
                    )
                    unsold_players = Player.search(
                        t_domain + [('state', '=', 'unsold')],
                        order='sl_no asc, name asc',
                    )
                    Tier = request.env['auction.player.tier'].sudo()
                    tiers = Tier.search(
                        [('tournament_id', '=', tournament_id.id)],
                        order='name asc',
                    )
                    if not tiers:
                        tiers = (draft_players | unsold_players).mapped('tier_id')
                    html = self._render_auction_resume(
                        tournament_id, db_name, theme, auction_ids,
                        draft_players, unsold_players, Player.browse(),
                        draft_count, unsold_count, sold_count, 0,
                        tiers, squads_full=False,
                    )
                elif sold_count:
                    html = _thank_you_html()
                else:
                    html = request.render("auction_module.welcome_message_template", {
                        'tournament': tournament_id,
                        'theme': theme,
                        'db_name': db_name,
                    }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    def _resume_resolve_tournament(self, db_name, tournament_slug):
        """Resolve tournament inside an already-opened db context."""
        if not tournament_slug:
            return request.env['auction.tournament'].sudo().browse()
        return request.env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )

    def _resume_parse_player_ids(self):
        """Accept player ids from form field, query string, or JSON body."""
        import json as _json
        ids = []
        values = request.httprequest.values
        # Repeated fields or single comma-separated value
        raw_list = values.getlist('player_ids') if hasattr(values, 'getlist') else []
        if not raw_list:
            raw = values.get('player_ids') or request.params.get('player_ids')
            if raw not in (None, False, ''):
                raw_list = [raw]
        for item in raw_list:
            ids.extend(str(item).split(','))
        if not ids:
            try:
                body = request.httprequest.get_data(as_text=True) or ''
                if body.strip().startswith('{'):
                    data = _json.loads(body)
                    for item in (data.get('player_ids') or []):
                        ids.append(str(item))
            except Exception:
                pass
        out = []
        for x in ids:
            x = str(x).strip()
            if x.isdigit():
                out.append(int(x))
        return out

    def _resume_open_players(self, tournament, player_ids):
        """Move draft/unsold players to auction and stage the next presentation player."""
        Player = request.env['auction.team.player'].sudo()
        players = Player.browse(player_ids).exists().filtered(
            lambda p: p.tournament_id.id == tournament.id
            and not p.icon_player
            and p.state in ('draft', 'unsold')
        )
        if not players:
            return players
        # Direct write — avoid notify_success (breaks on auth=none / public env)
        players.write({'state': 'auction'})
        tournament.sudo().write({'auction_declared_complete': False})
        # Put a player on stage so display_auction shows the presentation immediately
        try:
            Player.get_random_player(tournament_id=tournament)
        except Exception:
            pass
        return players

    @http.route(
        [
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/open',
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/open/',
        ],
        type='http', auth='none', website=False, csrf=False, methods=['POST', 'GET'],
    )
    def display_auction_resume_open(self, db_name, tournament_slug, **kw):
        """Open Draft and/or Unsold players into auction, then resume presentation."""
        import json as _json
        result = {'ok': False, 'error': 'Unknown error', 'redirect': None, 'opened': 0}
        with self._with_db(db_name) as ok:
            if not ok:
                result['error'] = 'Database not found'
            else:
                tournament = self._resume_resolve_tournament(db_name, tournament_slug)
                display_url = '/%s/auction/display_auction/%s/' % (db_name, tournament_slug)
                result['redirect'] = display_url
                if not tournament:
                    result['error'] = 'Tournament not found'
                else:
                    player_ids = self._resume_parse_player_ids()
                    if not player_ids:
                        result['error'] = 'No players selected'
                    else:
                        players = self._resume_open_players(tournament, player_ids)
                        if not players:
                            result['error'] = 'No eligible players found'
                        else:
                            result = {
                                'ok': True,
                                'opened': len(players),
                                'redirect': display_url,
                                'error': None,
                            }
        # Prefer browser redirect (form submit) so presentation reloads reliably
        wants_json = 'application/json' in (request.httprequest.headers.get('Accept') or '')
        if result.get('ok') and not wants_json:
            return werkzeug.utils.redirect(result['redirect'], 303)
        status = 200 if result.get('ok') else 400
        return request.make_response(
            _json.dumps(result),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )

    @http.route(
        [
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/complete',
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/complete/',
        ],
        type='http', auth='none', website=False, csrf=False, methods=['POST', 'GET'],
    )
    def display_auction_resume_complete(self, db_name, tournament_slug, **kw):
        """Declare auction complete and go to the Thank You screen.

        Also clears on-stage / dice so the projector switches to its Thank You
        ceremony on the next poll (not stuck on a leftover player card).
        """
        import json as _json
        display_url = '/%s/auction/display_auction/%s/' % (db_name, tournament_slug)
        result = {'ok': False, 'error': 'Unknown error', 'redirect': display_url}
        with self._with_db(db_name) as ok:
            if not ok:
                result['error'] = 'Database not found'
            else:
                tournament = self._resume_resolve_tournament(db_name, tournament_slug)
                if not tournament:
                    result['error'] = 'Tournament not found'
                else:
                    Player = request.env['auction.team.player'].sudo().with_context(
                        saas_skip_freeze=True,
                    )
                    on_stage = Player.search([
                        ('tournament_id', '=', tournament.id),
                        ('is_on_stage', '=', True),
                    ])
                    if on_stage:
                        on_stage.write({'is_on_stage': False})
                    try:
                        tournament.set_dice_state('idle', 0)
                    except Exception:
                        pass
                    tournament.sudo().with_context(saas_skip_freeze=True).write({
                        'auction_declared_complete': True,
                        'stamp_player_id': False,
                        'stamp_state': False,
                        'stamp_expires_at': False,
                        'break_time_active': False,
                        # Thank You must override live pool/fixture board on projector
                        'projector_board_mode': 'idle',
                        'projector_board_reveal_until': False,
                    })
                    result = {'ok': True, 'redirect': display_url, 'error': None}
        wants_json = 'application/json' in (request.httprequest.headers.get('Accept') or '')
        if result.get('ok') and not wants_json:
            return werkzeug.utils.redirect(result['redirect'], 303)
        status = 200 if result.get('ok') else 400
        return request.make_response(
            _json.dumps(result),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )

    @http.route(
        [
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/mark-unsold',
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/mark-unsold/',
        ],
        type='http', auth='none', website=False, csrf=False, methods=['POST', 'GET'],
    )
    def display_auction_resume_mark_unsold(self, db_name, tournament_slug, **kw):
        """Mark all remaining In-Auction players as unsold when every squad is full."""
        import json as _json
        display_url = '/%s/auction/display_auction/%s/' % (db_name, tournament_slug)
        result = {'ok': False, 'error': 'Unknown error', 'redirect': display_url, 'marked': 0}
        with self._with_db(db_name) as ok:
            if not ok:
                result['error'] = 'Database not found'
            else:
                tournament = self._resume_resolve_tournament(db_name, tournament_slug)
                if not tournament:
                    result['error'] = 'Tournament not found'
                elif not self._tournament_all_squads_full(tournament):
                    result['error'] = 'Team squads are not all full yet'
                else:
                    players = self._resume_mark_auction_unsold(tournament)
                    result = {
                        'ok': True,
                        'redirect': display_url,
                        'marked': len(players),
                        'error': None,
                    }
        wants_json = 'application/json' in (request.httprequest.headers.get('Accept') or '')
        if result.get('ok') and not wants_json:
            return werkzeug.utils.redirect(result['redirect'], 303)
        status = 200 if result.get('ok') else 400
        return request.make_response(
            _json.dumps(result),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )

    @http.route(
        [
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/reopen',
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/resume/reopen/',
        ],
        type='http', auth='none', website=False, csrf=False, methods=['POST', 'GET'],
    )
    def display_auction_resume_reopen(self, db_name, tournament_slug, **kw):
        """Clear declared-complete so Draft/Unsold can be opened again."""
        display_url = '/%s/auction/display_auction/%s/' % (db_name, tournament_slug)
        with self._with_db(db_name) as ok:
            if ok:
                tournament = self._resume_resolve_tournament(db_name, tournament_slug)
                if tournament:
                    tournament.sudo().write({'auction_declared_complete': False})
        return werkzeug.utils.redirect(display_url, 303)

    @http.route(
        [
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/print-roster',
            '/<string:db_name>/auction/display_auction/<string:tournament_slug>/print-roster/',
        ],
        type='http', auth='none', website=False, csrf=False, methods=['GET', 'POST'],
    )
    def display_auction_print_roster(self, db_name, tournament_slug, **kw):
        """Print squad roster PDF for one or more teams (same report as button_print_roster)."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = self._resume_resolve_tournament(db_name, tournament_slug)
            if not tournament:
                return self._not_found()

            raw = kw.get('ids') or request.params.get('ids') or ''
            if isinstance(raw, (list, tuple)):
                raw_parts = []
                for item in raw:
                    raw_parts.extend(str(item).split(','))
            else:
                raw_parts = str(raw).split(',')
            auction_ids = []
            for part in raw_parts:
                part = str(part).strip()
                if part.isdigit():
                    auction_ids.append(int(part))
            # Deduplicate while preserving order
            seen = set()
            auction_ids = [i for i in auction_ids if not (i in seen or seen.add(i))]
            if not auction_ids:
                return request.make_response(
                    'No teams selected.',
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=400,
                )

            Auction = request.env['auction.auction'].sudo()
            auctions = Auction.search([
                ('id', 'in', auction_ids),
                ('tournament_id', '=', tournament.id),
            ])
            # Keep selection order
            by_id = {a.id: a for a in auctions}
            ordered = Auction.browse([i for i in auction_ids if i in by_id])
            if not ordered:
                return request.make_response(
                    'No matching teams found for this tournament.',
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=404,
                )

            try:
                report = request.env.ref('auction_module.action_report_auction_players').sudo()
                pdf_files = self._roster_pdfs_per_team(report, ordered, db_name)
            except Exception:
                _logger.exception(
                    'Roster PDF failed for tournament=%s auctions=%s',
                    tournament.id, ordered.ids,
                )
                return request.make_response(
                    'Could not generate roster PDF.',
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=500,
                )

            if len(pdf_files) == 1:
                filename, pdf_content = pdf_files[0]
                return request.make_response(
                    pdf_content,
                    headers=[
                        ('Content-Type', 'application/pdf'),
                        ('Content-Length', str(len(pdf_content))),
                        ('Content-Disposition', 'attachment; filename="%s"' % filename),
                    ],
                )

            import io
            import zipfile
            zip_buf = io.BytesIO()
            used_names = {}
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for name, content in pdf_files:
                    base = name
                    if base in used_names:
                        used_names[base] += 1
                        stem = base[:-4] if base.lower().endswith('.pdf') else base
                        name = '%s_%d.pdf' % (stem, used_names[base])
                    else:
                        used_names[base] = 1
                    zf.writestr(name, content)
            zip_content = zip_buf.getvalue()
            tourn_safe = re.sub(r'[^\w\-]+', '_', tournament.name or 'Auction').strip('_') or 'Auction'
            zip_name = '%s_Squad_Rosters.zip' % tourn_safe
            return request.make_response(
                zip_content,
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Length', str(len(zip_content))),
                    ('Content-Disposition', 'attachment; filename="%s"' % zip_name),
                ],
            )

    def _roster_pdf_filename(self, auction):
        team_name = (auction.team_id.name if auction.team_id else 'Team') or 'Team'
        safe = re.sub(r'[^\w\-]+', '_', team_name).strip('_') or 'Team'
        return '%s_Squad_Roster.pdf' % safe

    def _roster_split_pdf_evenly(self, pdf_bytes, n_docs):
        """Split a combined roster PDF into one PDF per team.

        Handles common wkhtmltopdf layouts:
        - exactly N pages (1 page/team)
        - N+1 pages (trailing blank)
        - K*N pages (same page count per team)
        """
        if n_docs <= 1 or not pdf_bytes:
            return None
        import io
        try:
            try:
                from odoo.tools.pdf import PdfFileReader, PdfFileWriter
            except ImportError:
                try:
                    from PyPDF2 import PdfFileReader, PdfFileWriter
                except ImportError:
                    from PyPDF2 import PdfReader as PdfFileReader, PdfWriter as PdfFileWriter

            reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
            if hasattr(reader, 'getNumPages'):
                n_pages = reader.getNumPages()
                pages = [reader.getPage(i) for i in range(n_pages)]
            else:
                pages = list(reader.pages)
                n_pages = len(pages)
            if n_pages < n_docs:
                return None

            # Drop a single trailing blank page when present
            if n_pages == n_docs + 1:
                pages = pages[:n_docs]
                n_pages = n_docs

            if n_pages % n_docs != 0:
                return None
            chunk = n_pages // n_docs
            out = []
            for i in range(n_docs):
                writer = PdfFileWriter()
                for page in pages[i * chunk:(i + 1) * chunk]:
                    if hasattr(writer, 'addPage'):
                        writer.addPage(page)
                    else:
                        writer.add_page(page)
                buf = io.BytesIO()
                writer.write(buf)
                out.append(buf.getvalue())
            return out
        except Exception:
            _logger.warning('Could not split combined roster PDF', exc_info=True)
            return None

    def _roster_pdfs_per_team(self, report, auctions, db_name):
        """Build one PDF per auction using a single wkhtmltopdf pass when possible."""
        auctions = auctions.exists()
        if not auctions:
            return []

        names = [self._roster_pdf_filename(a) for a in auctions]
        if len(auctions) == 1:
            pdf_content, _mime = report._render_qweb_pdf(auctions.ids)
            return [(names[0], pdf_content)]

        # One render for all teams (much faster than N separate wkhtmltopdf runs)
        combined, _mime = report._render_qweb_pdf(auctions.ids)
        split = self._roster_split_pdf_evenly(combined, len(auctions))
        if split:
            return list(zip(names, split))

        # Page counts uneven — render each team once in parallel (still separate PDFs)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        auction_ids = auctions.ids
        id_to_name = dict(zip(auction_ids, names))
        results = {}

        def _render_one(auction_id):
            registry = odoo.registry(db_name)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                rep = env.ref('auction_module.action_report_auction_players').sudo()
                pdf_content, _mime = rep._render_qweb_pdf([auction_id])
                return auction_id, pdf_content

        workers = min(4, len(auction_ids))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_render_one, aid) for aid in auction_ids]
            for fut in as_completed(futures):
                aid, pdf_content = fut.result()
                results[aid] = pdf_content

        return [(id_to_name[aid], results[aid]) for aid in auction_ids]

    def _remaining_players_ctx(self, tournament, theme):
        """Build the render context for the Remaining Players drawer."""
        t_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        players = request.env['auction.team.player'].sudo().search(
            t_domain + [('state', '=', 'auction'), ('icon_player', '=', False)],
            order='sl_no asc',
        )
        # Group players by tier (preserving encounter order)
        tier_map = {}
        tier_order = []
        for p in players:
            key = p.tier_id.id if p.tier_id else 0
            if key not in tier_map:
                tier_order.append(key)
                tier_map[key] = {
                    'tier_name': p.tier_id.name if p.tier_id else 'General',
                    'color':     p.tier_id.color if p.tier_id else '#7f8c8d',
                    'players':   [],
                }
            tier_map[key]['players'].append(p)
        tier_groups = [tier_map[k] for k in tier_order]
        return {
            'tier_groups':  tier_groups,
            'total_count':  len(players),
            'theme':        theme,
            'res_company':  request.env['res.company'].sudo().search([], limit=1),
        }

    @http.route('/auction/display_auction/remaining-players', type='http', auth='public', website=True, sitemap=False)
    def display_remaining_players(self, **kwargs):
        """Standalone page loaded inside the Remaining Players drawer iframe (legacy single-db)."""
        tournament = self._resolve_tournament()
        theme = kwargs.get('theme', '') or (tournament.player_display_template if tournament else '') or 'vanilla'
        return request.render('auction_module.remaining_players_template',
                              self._remaining_players_ctx(tournament, theme))

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/display_auction/remaining-players',
                type='http', auth='none', website=False, sitemap=False)
    def display_remaining_players_db(self, db_name, tournament_slug, **kwargs):
        """DB-aware variant so the drawer loads on multi-database instances."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            theme = kwargs.get('theme', '') or (tournament.player_display_template if tournament else '') or 'vanilla'
            html = request.render('auction_module.remaining_players_template',
                                  self._remaining_players_ctx(tournament, theme), lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    def _team_players_render(self, team_id, tournament_slug=None, db_name=None, **kwargs):
        """Build (template_ref, ctx) for a team's squad/roster page.

        Tournament resolution (multi-active tournaments):
        1. Explicit *tournament_slug* from the URL
        2. The team's own ``tournament_id``
        3. Legacy ``_resolve_tournament()`` fallback
        """
        player_data_list = []
        team = request.env['auction.team'].sudo().browse(team_id)

        tournament = request.env['auction.tournament'].sudo()
        if tournament_slug:
            tournament = tournament.search([('slug', '=', tournament_slug)], limit=1)
        if not tournament and team.exists():
            tournament = team.tournament_id
        if not tournament:
            tournament = self._resolve_tournament()

        auction_domain = [('auction_id.team_id', '=', team_id)]
        if tournament:
            auction_domain.append(('auction_id.tournament_id', '=', tournament.id))
        team_players = request.env['auction.auction.player'].sudo().search(auction_domain)

        theme = (tournament.player_display_template if tournament else None) or 'vanilla'
        icon_players = request.env['auction.team.player'].sudo().get_icon_players(team_id)
        if icon_players:
            for icon in icon_players:
                player_data = {
                    'name': icon.name,
                    'photo': icon.photo,
                    'point': 'ICON',
                    'role': icon.role,
                    'batting_style': icon.batting_style,
                    'bowling_style': icon.bowling_style,
                    'contact': icon.contact,
                    'p_type': icon.p_type,
                    'p_category': icon.p_category,
                    'tier_color': icon.tier_id.color if icon.tier_id else '#01cfff',
                    'tier_name': icon.tier_id.name if icon.tier_id else 'Icon',
                    'is_icon': True,
                }
                player_data_list.append(player_data)
        if team_players:
            for player in team_players:
                player_data = {
                    'name': player.player_id.name,
                    'photo': player.player_id.photo,
                    'point': player.points,
                    'role': player.player_id.role,
                    'batting_style': player.player_id.batting_style,
                    'bowling_style': player.player_id.bowling_style,
                    'contact': player.player_id.contact,
                    'p_type': player.player_id.p_type,
                    'p_category': player.player_id.p_category,
                    'tier_color': player.player_id.tier_id.color if player.player_id.tier_id else '#01cfff',
                    'tier_name': player.player_id.tier_id.name if player.player_id.tier_id else '',
                    'is_icon': False,
                }
                player_data_list.append(player_data)
        players_template_map = {
            'pistah': 'auction_module.auction_team_players_template_pistah',
            'blackberry': 'auction_module.auction_team_players_template_blackberry',
        }
        template_ref = players_template_map.get(theme, 'auction_module.auction_team_players_template')
        resolved_slug = tournament_slug or (tournament.slug if tournament else '')
        q = request.httprequest.args
        from_projector = (kwargs.get('from') or q.get('from') or '') == 'projector'
        mode = kwargs.get('mode') or q.get('mode') or (
            'light' if theme in ('lemon', 'strawberry') else 'dark')
        if mode not in ('dark', 'light'):
            mode = 'dark'
        ctx = {
            'players': player_data_list,
            'team': team,
            'tournament': tournament,
            'theme': theme,
            'db_name': db_name or request.env.cr.dbname,
            'tournament_slug': resolved_slug,
            'from_projector': from_projector,
            'mode': mode,
        }
        return template_ref, ctx

    @http.route('/auction/get/players/team/<int:team_id>', type='http', auth='public', website=True)
    def get_team_players(self, team_id, **kwargs):
        template_ref, ctx = self._team_players_render(team_id, **kwargs)
        return request.render(template_ref, ctx)

    @http.route('/<string:db_name>/auction/get/players/team/<int:team_id>',
                type='http', auth='none', website=False, sitemap=False)
    def get_team_players_db(self, db_name, team_id, **kwargs):
        """DB-aware variant so the roster loads on multi-database instances."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            template_ref, ctx = self._team_players_render(team_id, db_name=db_name, **kwargs)
            html = request.render(template_ref, ctx, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/get/players/team/<int:team_id>',
                type='http', auth='none', website=False, sitemap=False)
    def get_team_players_db_slug(self, db_name, tournament_slug, team_id, **kwargs):
        """Canonical squad URL scoped by database + tournament slug."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            template_ref, ctx = self._team_players_render(
                team_id, tournament_slug=tournament_slug, db_name=db_name, **kwargs)
            html = request.render(template_ref, ctx, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/get_players/<int:team_id>', type='json', auth="user", methods=['POST'], csrf=False)
    def get_players(self, team_id):
        team = request.env['auction.team'].browse(team_id)
        try:

            players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])


            player_data = []
            icon_players = team.key_player_ids
            if icon_players:
                for icon_player in icon_players:
                        player_data.append({
                            'name': icon_player.name,
                            'points': 'ICON PLAYER',
                            'role': icon_player.role,
                            'contact': icon_player.contact,
                            'c': icon_player.photo
                        })
            if players:
                for player in players:
                    player_data.append({
                        'name': player.player_id.name,
                        'points': player.points,
                        'role': player.player_id.role,
                        'contact': player.contact,
                        'photo': player.player_id.photo
                    })
            else:
                return {'status': 'error', 'message': 'No players found', 'team': team.name}
            return {'status': 'success', 'players': player_data, 'team': team.name, 'team_obj': team}

        except Exception as e:
            # Log the exception
            return {'status': 'error', 'message': str(e), 'team': team.name}

    # @http.route('/get_players/<int:team_id>', type='http', auth="user", csrf=False)
    # def get_players(self, team_id):
    #     players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])
    #     team = request.env['auction.team'].browse(team_id)
    #
    #     player_data = []
    #     print(players, "===============>")
    #     for player in players:
    #         player_data.append({
    #             'name': player.player_id.name,
    #             'points': player.points,
    #             'role': player.player_id.role,
    #             'contact': player.contact
    #         })
    #
    #     return {'status': 'success', 'players': player_data, 'team': team.name}

    @http.route('/player_card/download', type='http', auth="public", website=True)
    def download_player_card(self,  **kwargs):

        tournament = self._resolve_tournament()

        players = request.env['auction.team.player'].sudo().search([('state', 'in', ['draft', 'auction'])], limit=3)
        html_content = ''
        if players:
            for player in players:
                html_content += request.env['ir.ui.view']._render_template('auction_module.player_card_template', {
                    'player': player,
                    'tournament': tournament
                })
                # Add a page break after each player card
        # Convert HTML to PDF
        # paper_format = request.env.ref('auction_module.paperformat_euro_landscaoe')
        report_obj = request.env.ref('auction_module.action_player_card_print_template')
        pdf = report_obj._run_wkhtmltopdf(
            [html_content], header=None, footer=None
        )

        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="Player Cards.pdf"')
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)

    @http.route('/player_card/download_images', type='http', auth="public", website=True)
    def download_player_cards_as_images(self, **kwargs):
        tournament = self._resolve_tournament()


        # Fetch all players related to the tournament
        players = request.env['auction.team.player'].sudo().get_auction_players(tournament_id=tournament)

        image_paths = []
        with tempfile.TemporaryDirectory() as tmpdirname:
            for player in players:
                # Render the HTML for the player
                html_content = request.env['ir.ui.view']._render_template('auction_module.player_card_template', {
                    'player': player,
                    'tournament': tournament
                })
                # Save the HTML to a temporary file
                html_file = os.path.join(tmpdirname, f"player_{player.id}.html")
                with open(html_file, 'w') as f:
                    f.write(html_content)

                # Convert the HTML to an image using wkhtmltoimage
                image_file = os.path.join(tmpdirname, f"player_{player.id}.jpg")
                command = [
                    'wkhtmltoimage',
                    '--quality', '75',
                    '--width', '1080',
                    '--disable-smart-width',
                    '--format', 'jpg',
                    html_file, image_file
                ]
                # command = ['wkhtmltoimage', '--quality', '100', '--format', 'jpg', html_file, image_file]
                subprocess.run(command, check=True)

                image_paths.append(image_file)

            # Create a ZIP file containing all the images
            zip_file_path = os.path.join(tmpdirname, "player_cards.zip")
            command = ['zip', '-j', zip_file_path] + image_paths
            subprocess.run(command, check=True)

            with open(zip_file_path, 'rb') as f:
                zip_data = f.read()

        # Serve the ZIP file for download
        response = request.make_response(
            zip_data,
            headers=[
                ('Content-Type', 'application/zip'),
                ('Content-Disposition', 'attachment; filename="player_cards.zip"'),
            ]
        )
        return response

    @http.route('/auction/live', type='http', auth='public', website=True)
    def auction_live_page(self, **kw):
        return request.render('auction_module.auction_live_page')

    @http.route('/auction/my/live-board', type='http', auth='user', website=False)
    def my_live_board_redirect(self, **kw):
        """Menu shortcut: resolve the current user's tournament and redirect to its live board."""
        user = request.env['res.users'].sudo().browse(request.uid)
        tournament = user.tournament_id
        if not tournament:
            # Admin has no specific tournament — fall back to active tournament
            is_admin = request.env.user.has_group('auction_module.group_auction_group_admin')
            if is_admin:
                tournament = request.env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1
                )
        if tournament and tournament.slug:
            db_name = request.env.cr.dbname
            resp = request.redirect('/{}/{}/auction/live-board'.format(db_name, tournament.slug))
            return self._live_board_grant_access(tournament, response=resp)
        return request.redirect('/web')

    @http.route('/auction/my/team-balance', type='http', auth='user', website=False)
    def my_team_balance_redirect(self, **kw):
        """Menu shortcut: resolve the current user's tournament and redirect to its points table."""
        tournament = request.env.user.sudo().tournament_id
        if not tournament:
            tournament = request.env['auction.tournament'].sudo().search(
                [('active', '=', True)], limit=1
            )
        if tournament and tournament.slug:
            return request.redirect('/{}/auction/show/team/balance'.format(tournament.slug))
        return request.redirect('/web')

    # ─────────────────────────────────────────────────────────────────
    #  PAYMENT MARKER  (web page + toggle JSON endpoint)
    # ─────────────────────────────────────────────────────────────────

    def _get_pm_access(self):
        """Return (has_access: bool, is_admin: bool). Calls has_group once per group (cached in Odoo)."""
        user = request.env.user
        is_admin = user.has_group('auction_module.group_auction_group_admin')
        has_access = (
            is_admin
            or user.has_group('auction_module.group_auction_group')
            or user.has_group('auction_module.group_auction_payment_marker')
        )
        return has_access, is_admin

    def _check_payment_marker_access(self):
        """Kept for backward compat — delegates to _get_pm_access."""
        has_access, _ = self._get_pm_access()
        return has_access

    @staticmethod
    def _safe_json(data):
        """JSON-encode data and escape <, >, & so it is safe inside a <script> tag in XML."""
        s = json.dumps(data, ensure_ascii=False)
        return s.replace('&', r'\u0026').replace('<', r'\u003c').replace('>', r'\u003e')

    def _pm_user_can_access_tournament(self, tournament):
        """True when the current user may open Payment Tracker for ``tournament``.

        Accepts:
        - Auction admins
        - Working / profile tournament (incl. SaaS session switcher)
        - Any tournament in ``user.tournament_ids``
        - Tournaments owned by the user's SaaS account
        """
        if not tournament:
            return False
        _has_access, is_admin = self._get_pm_access()
        if is_admin:
            return True

        user = request.env.user.sudo()
        tid = tournament.id

        working = self._resolve_tournament()
        if working and working.id == tid:
            return True

        if user.tournament_id and user.tournament_id.id == tid:
            return True

        try:
            if tid in (user.tournament_ids.ids or []):
                return True
        except Exception:
            pass

        # SaaS organiser: any tournament on their account
        try:
            account = getattr(tournament, 'saas_account_id', False)
            if account and account.user_id and account.user_id.id == user.id:
                return True
        except Exception:
            pass

        return False

    def _resolve_payment_marker_url(self, tournament_id=None):
        """Resolve the Payment Tracker page URL for the current user.

        Returns ``(url, error_message)``. Used by the client action and the
        legacy redirect route so SaaS / non-SaaS share one code path.
        """
        has_access, is_admin = self._get_pm_access()
        if not has_access:
            return None, 'Access denied'

        env = request.env
        db_name = env.cr.dbname
        tournament = env['auction.tournament']

        if tournament_id:
            try:
                tid = int(tournament_id)
            except (TypeError, ValueError):
                return None, 'Invalid tournament'
            tournament = env['auction.tournament'].sudo().browse(tid)
            if not tournament.exists():
                return None, 'Tournament not found'
            if not self._pm_user_can_access_tournament(tournament):
                return None, 'Access denied — wrong tournament'
        else:
            tournament = self._resolve_tournament()
            if not tournament and is_admin:
                tournament = env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1
                )
            if tournament and not self._pm_user_can_access_tournament(tournament):
                tournament = env['auction.tournament']

        if not tournament or not tournament.slug:
            return None, (
                'No tournament assigned. Ask an administrator to assign a '
                'tournament, or create one first.'
            )

        url = '/{}/{}/auction/payment-marker'.format(db_name, tournament.slug)
        return url, None

    def _payment_marker_payload(self, tournament):
        """Build the Payment Tracker data dict (players, stats, teams, URLs)."""
        env = request.env
        db_name = env.cr.dbname
        tournament_id = tournament.id
        tournament_slug = tournament.slug or ''
        _has_access, is_admin = self._get_pm_access()
        tournament_choices, show_tournament_filter, is_saas = (
            self._pm_tournament_filter_meta()
        )

        PLAYER_FIELDS = [
            'id', 'sl_no', 'name', 'role', 'contact',
            'state', 'amount_paid', 'payment_url',
            'assigned_team_id', 'tier_id',
        ]
        rows = env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        ).search_read(
            [('tournament_id', '=', tournament_id)],
            fields=PLAYER_FIELDS,
            order='sl_no asc, name asc',
        )

        to_mark_ids = [r['id'] for r in rows if r['payment_url'] and not r['amount_paid']]
        if to_mark_ids:
            env['auction.team.player'].sudo().with_context(
                auction_skip_tournament_security=True,
            ).browse(to_mark_ids).write({'amount_paid': True})
            mark_set = set(to_mark_ids)
            for r in rows:
                if r['id'] in mark_set:
                    r['amount_paid'] = True

        proof_ids = set()
        if rows:
            env.cr.execute(
                """
                SELECT DISTINCT res_id
                  FROM ir_attachment
                 WHERE res_model = 'auction.team.player'
                   AND res_field = 'payment_proof'
                   AND res_id = ANY(%s)
                """,
                ([r['id'] for r in rows],),
            )
            proof_ids = {row[0] for row in env.cr.fetchall()}

        team_ids = list({r['assigned_team_id'][0] for r in rows if r['assigned_team_id']})
        teams_map = {}
        if team_ids:
            for t in env['auction.team'].sudo().with_context(
                auction_skip_tournament_security=True,
            ).browse(team_ids).read(['id', 'name', 'manager', 'logo']):
                teams_map[t['id']] = {
                    'name':     t['name'] or '',
                    'manager':  t['manager'] or '',
                    'has_logo': bool(t['logo']),
                }

        def _mask(c):
            c = str(c or '')
            return (c[0] + 'X' * (len(c) - 2) + c[-1]) if len(c) > 2 else c

        STATE_LABELS = {
            'draft': 'Draft', 'auction': 'In Auction',
            'sold': 'Sold', 'unsold': 'Unsold',
        }
        players_data = []
        for r in rows:
            team_id = r['assigned_team_id'][0] if r['assigned_team_id'] else None
            team = teams_map.get(team_id, {})
            players_data.append({
                'id':                r['id'],
                'sl_no':             r['sl_no'] or 0,
                'name':              r['name'] or '',
                'role':              r['role'] or '',
                'contact':           r['contact'] or '',
                'masked_contact':    _mask(r['contact']),
                'state':             r['state'],
                'state_label':       STATE_LABELS.get(r['state'], r['state']),
                'amount_paid':       bool(r['amount_paid']),
                'has_payment_url':   bool(r['payment_url']),
                'proof_att_id':      1 if r['id'] in proof_ids else 0,
                'proof_data':        '',
                'team':              team.get('name', ''),
                'manager':           team.get('manager', ''),
                'tier':              r['tier_id'][1] if r['tier_id'] else '',
            })

        total = len(players_data)
        paid_total = sum(1 for p in players_data if p['amount_paid'])
        by_state = {st: [0, 0] for st in ('draft', 'auction', 'sold', 'unsold')}
        for p in players_data:
            bucket = by_state.get(p['state'])
            if bucket:
                bucket[0] += 1
                if p['amount_paid']:
                    bucket[1] += 1

        logo_url = ''
        if tournament.logo:
            logo_url = '/web/image/auction.tournament/%s/logo' % tournament.id

        return {
            'ok': True,
            'tournament': {
                'id': tournament.id,
                'name': tournament.name or '',
                'slug': tournament_slug,
                'logo_url': logo_url,
            },
            'players': players_data,
            'stats': {
                'total': total,
                'paid': paid_total,
                'unpaid': total - paid_total,
                'by_state': {
                    st: {'total': v[0], 'paid': v[1]} for st, v in by_state.items()
                },
            },
            'teams': sorted(
                [{'id': tid, 'name': t['name'], 'has_logo': t['has_logo']}
                 for tid, t in teams_map.items()],
                key=lambda t: t['name'],
            ),
            'urls': {
                'toggle': '/{}/{}/auction/payment-marker/toggle'.format(
                    db_name, tournament_slug
                ),
                'proof_base': '/{}/{}/auction/payment-marker/proof/'.format(
                    db_name, tournament_slug
                ),
                'upload': '/{}/{}/auction/payment-marker/upload-proof'.format(
                    db_name, tournament_slug
                ),
                'unlink': '/{}/{}/auction/payment-marker/unlink-proof'.format(
                    db_name, tournament_slug
                ),
            },
            'is_admin': is_admin,
            'page_size': 40,
            'show_tournament_filter': show_tournament_filter,
            'tournaments': tournament_choices,
            'is_saas': is_saas,
        }

    def _pm_tournament_filter_meta(self):
        """Tournament dropdown choices + whether to show the filter.

        SaaS organisers: locked to working tournament (no dropdown).
        Admins: all active tournaments.
        Other users: their assigned tournament_ids (dropdown if more than one).
        """
        _has_access, is_admin = self._get_pm_access()
        env = request.env
        is_saas = False
        try:
            Acc = env['ac.saas.account']
            is_saas = bool(Acc._get_account_for_user())
        except Exception:
            is_saas = False

        if is_saas and not is_admin:
            return [], False, True

        if is_admin:
            tournaments = env['auction.tournament'].sudo().search(
                [('active', '=', True)], order='name asc, id asc'
            )
        else:
            user = env.user.sudo()
            tournaments = user.tournament_ids.filtered(lambda t: t.active)
            if not tournaments and user.tournament_id:
                tournaments = user.tournament_id

        choices = [{'id': t.id, 'name': t.name or ('Tournament #%s' % t.id)}
                   for t in tournaments]
        show = bool(is_admin or len(choices) > 1)
        return choices, show, is_saas

    def _render_payment_marker_page(self, tournament, embed=False):
        """Build the Payment Tracker HTML response for a resolved tournament."""
        env = request.env
        payload = self._payment_marker_payload(tournament)
        company = env['res.company'].sudo().search([], limit=1)
        html = request.render('auction_module.payment_marker_template', {
            'tournament':     tournament,
            'players_json':   self._safe_json(payload['players']),
            'stats_json':     self._safe_json(payload['stats']),
            'teams_json':     self._safe_json(payload['teams']),
            'toggle_url':     payload['urls']['toggle'],
            'proof_base_url': payload['urls']['proof_base'],
            'upload_url':     payload['urls']['upload'],
            'unlink_url':     payload['urls']['unlink'],
            'is_admin':       payload['is_admin'],
            'res_company':    company,
            'embed':          bool(embed),
        }, lazy=False)
        headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('X-Frame-Options', 'SAMEORIGIN'),
            ('Cache-Control', 'private, max-age=0, must-revalidate'),
        ]
        return request.make_response(html, headers)

    def _resolve_pm_tournament_record(self, tournament_id=None):
        """Return (tournament, error) for Payment Tracker routes."""
        has_access, is_admin = self._get_pm_access()
        if not has_access:
            return request.env['auction.tournament'], 'Access denied'

        env = request.env
        tournament = env['auction.tournament']

        if tournament_id:
            try:
                tid = int(tournament_id)
            except (TypeError, ValueError):
                return tournament, 'Invalid tournament'
            tournament = env['auction.tournament'].sudo().browse(tid)
            if not tournament.exists():
                return env['auction.tournament'], 'Tournament not found'
            if not self._pm_user_can_access_tournament(tournament):
                return env['auction.tournament'], 'Access denied — wrong tournament'
            return tournament, None

        tournament = self._resolve_tournament()
        if not tournament and is_admin:
            tournament = env['auction.tournament'].sudo().search(
                [('active', '=', True)], limit=1
            )
        if not tournament:
            return env['auction.tournament'], (
                'No tournament assigned. Ask an administrator to assign a '
                'tournament, or create one first.'
            )
        if not self._pm_user_can_access_tournament(tournament):
            return env['auction.tournament'], 'Access denied — wrong tournament'
        return tournament, None

    @http.route('/auction/payment-marker/resolve', type='json', auth='user', website=False)
    def payment_marker_resolve(self, tournament_id=None, **kw):
        """JSON helper for legacy callers (embed URL). Prefer /data for client action."""
        tournament, error = self._resolve_pm_tournament_record(tournament_id=tournament_id)
        if error:
            return {'ok': False, 'error': error}
        embed_url = '/auction/payment-marker/embed'
        if tournament:
            embed_url += '?tournament_id=%s' % int(tournament.id)
        return {
            'ok': True,
            'url': embed_url,
            'tournament_id': tournament.id,
            'slug': tournament.slug or '',
        }

    @http.route('/auction/payment-marker/data', type='json', auth='user', website=False)
    def payment_marker_data(self, tournament_id=None, **kw):
        """JSON payload for the native Payment Tracker client action."""
        tournament, error = self._resolve_pm_tournament_record(tournament_id=tournament_id)
        if error:
            return {'ok': False, 'error': error}
        return self._payment_marker_payload(tournament)

    @http.route('/auction/payment-marker/embed', type='http', auth='user', website=False)
    def payment_marker_embed(self, tournament_id=None, **kw):
        """Auth'd embed page used by the backend client-action iframe."""
        tournament, error = self._resolve_pm_tournament_record(
            tournament_id=tournament_id or kw.get('tournament_id')
        )
        if error == 'Access denied' or error == 'Access denied — wrong tournament':
            return werkzeug.exceptions.Forbidden()
        if error or not tournament:
            return request.make_response(
                '<html><body style="font-family:sans-serif;padding:40px">'
                '<h2>Payment Tracker</h2>'
                '<p>%s</p></body></html>' % (
                    error or 'No tournament assigned.'
                ),
                [('Content-Type', 'text/html; charset=utf-8')]
            )
        return self._render_payment_marker_page(tournament, embed=True)

    @http.route('/auction/my/payment-marker', type='http', auth='user', website=False)
    def payment_marker_redirect(self, **kw):
        """Legacy bookmark URL → canonical payment-marker page (or error HTML)."""
        url, error = self._resolve_payment_marker_url(
            tournament_id=kw.get('tournament_id')
        )
        if error == 'Access denied':
            return werkzeug.exceptions.Forbidden()
        if error or not url:
            return request.make_response(
                '<html><body style="font-family:sans-serif;padding:40px">'
                '<h2>No tournament assigned</h2>'
                '<p>%s</p>'
                '<a href="/web">&#8592; Back</a></body></html>' % (
                    error or 'Ask an administrator to assign a tournament to your user profile.'
                ),
                [('Content-Type', 'text/html; charset=utf-8')]
            )
        embed = kw.get('embed')
        if embed:
            # Prefer dedicated embed route when possible
            tid = kw.get('tournament_id')
            if tid:
                return werkzeug.utils.redirect(
                    '/auction/payment-marker/embed?tournament_id=%s' % tid, 302
                )
            return werkzeug.utils.redirect('/auction/payment-marker/embed', 302)
        return werkzeug.utils.redirect(url, 302)

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker',
                type='http', auth='none', website=False)
    def payment_marker_page(self, db_name, tournament_slug, **kw):
        """Render the Payment Tracker web page (shareable / bookmark URL)."""
        # ── 1: Pin the URL's DB into the session (needed in multi-db mode) ──
        if request.session.db != db_name:
            try:
                valid_dbs = http.db_list(force=True)
            except Exception:
                valid_dbs = []
            if valid_dbs and db_name not in valid_dbs:
                return self._not_found()
            request.session.db = db_name
            return werkzeug.utils.redirect(request.httprequest.url, 302)

        # ── 2: Not logged in? Send to login (now bound to db_name), then back ──
        if not request.session.uid:
            target = request.httprequest.path
            qs = request.httprequest.query_string.decode()
            if qs:
                target += '?' + qs
            return werkzeug.utils.redirect(
                '/web/login?' + werkzeug.urls.url_encode({'redirect': target}), 302
            )

        # ── 3: auth='none' leaves uid unset — bind env to the logged-in user ──
        request.uid = request.session.uid
        request._env = None

        has_access, _is_admin = self._get_pm_access()
        if not has_access:
            return werkzeug.exceptions.Forbidden()

        tournament = request.env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )
        if not tournament:
            return self._not_found()

        if not self._pm_user_can_access_tournament(tournament):
            return werkzeug.exceptions.Forbidden()

        embed = str(kw.get('embed') or '').lower() in ('1', 'true', 'yes')
        return self._render_payment_marker_page(tournament, embed=embed)

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker/toggle',
                type='json', auth='user', website=False, csrf=False)
    def payment_marker_toggle(self, db_name, tournament_slug, player_id, paid, **kw):
        """Toggle amount_paid on a player. ≤3 DB hits (access cached, one read, one write)."""
        has_access, _is_admin = self._get_pm_access()
        if not has_access:
            return {'error': 'Access denied'}
        try:
            pid = int(player_id)
            env = request.env

            tourn = env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tourn:
                return {'error': 'Tournament not found'}

            if not self._pm_user_can_access_tournament(tourn):
                return {'error': 'Access denied — wrong tournament'}

            rows = env['auction.team.player'].sudo().with_context(
                auction_skip_tournament_security=True,
            ).search_read(
                [('id', '=', pid), ('tournament_id', '=', tourn.id)],
                ['id'], limit=1
            )
            if not rows:
                return {'error': 'Player not found'}

            new_val = bool(paid)
            env['auction.team.player'].sudo().with_context(
                auction_skip_tournament_security=True,
            ).browse(pid).write({'amount_paid': new_val})
            return {'success': True, 'amount_paid': new_val}
        except Exception:
            _logger.exception('payment_marker_toggle error')
            return {'error': 'Server error'}

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker/proof/<int:player_id>',
                type='http', auth='user', website=True, csrf=False)
    def payment_marker_proof(self, db_name, tournament_slug, player_id, **kw):
        """Serve payment proof image directly from filestore — no access check complexity."""
        has_access, _ = self._get_pm_access()
        if not has_access:
            return request.not_found()

        env = request.env
        env.cr.execute(
            "SELECT store_fname, db_datas, mimetype FROM ir_attachment "
            "WHERE res_model='auction.team.player' AND res_field='payment_proof' "
            "AND res_id = %s ORDER BY id DESC LIMIT 1",
            (player_id,)
        )
        row = env.cr.fetchone()
        if not row:
            return request.not_found()

        store_fname, db_datas, mimetype = row
        content = None

        if store_fname:
            filepath = os.path.join(
                odoo.tools.config['data_dir'], 'filestore', env.cr.dbname, store_fname
            )
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    content = f.read()

        if content is None and db_datas:
            content = base64.b64decode(db_datas)

        if content is None:
            return request.not_found()

        return request.make_response(content, headers=[
            ('Content-Type', mimetype or 'image/jpeg'),
            ('Cache-Control', 'private, max-age=3600'),
            ('Content-Length', str(len(content))),
        ])

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker/upload-proof',
                type='http', auth='user', website=True, csrf=False, methods=['POST'])
    def payment_marker_upload_proof(self, db_name, tournament_slug, **kw):
        """Upload payment proof screenshot, save to payment_proof field, mark player as paid."""
        def _json(data):
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')],
            )

        has_access, _ = self._get_pm_access()
        if not has_access:
            return _json({'error': 'Access denied'})

        try:
            player_id = int(kw.get('player_id') or request.httprequest.form.get('player_id', 0))
        except (ValueError, TypeError):
            return _json({'error': 'Invalid player_id'})

        upload_file = request.httprequest.files.get('file')
        if not player_id or not upload_file:
            return _json({'error': 'Missing player_id or file'})

        env = request.env
        tournament = env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )
        if not tournament:
            return _json({'error': 'Tournament not found'})

        if not self._pm_user_can_access_tournament(tournament):
            return _json({'error': 'Access denied — wrong tournament'})

        player = env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        ).search(
            [('id', '=', player_id), ('tournament_id', '=', tournament.id)], limit=1
        )
        if not player:
            return _json({'error': 'Player not found'})

        file_bytes = upload_file.read()
        # Binary field expects base64-encoded string, not bytes
        b64_str = base64.b64encode(file_bytes).decode('ascii')

        player.with_context(auction_skip_tournament_security=True).write({
            'payment_proof': b64_str,
            'amount_paid':   True,
        })

        # Build thumbnail data URI for immediate display
        proof_data = ''
        try:
            from PIL import Image as PILImage
            import io as _io
            img = PILImage.open(_io.BytesIO(file_bytes))
            img.thumbnail((900, 1200), PILImage.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format='JPEG', quality=82, optimize=True)
            proof_data = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception:
            mime = upload_file.content_type or 'image/jpeg'
            proof_data = 'data:{};base64,{}'.format(mime, b64_str)

        return _json({'success': True, 'proof_data': proof_data})

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker/unlink-proof',
                type='http', auth='user', website=True, csrf=False, methods=['POST'])
    def payment_marker_unlink_proof(self, db_name, tournament_slug, **kw):
        """Remove payment proof attachment from a player record."""
        def _json(data):
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')],
            )

        has_access, _ = self._get_pm_access()
        if not has_access:
            return _json({'error': 'Access denied'})

        try:
            player_id = int(kw.get('player_id') or request.httprequest.form.get('player_id', 0))
        except (ValueError, TypeError):
            return _json({'error': 'Invalid player_id'})

        if not player_id:
            return _json({'error': 'Missing player_id'})

        env = request.env
        tournament = env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )
        if not tournament:
            return _json({'error': 'Tournament not found'})

        if not self._pm_user_can_access_tournament(tournament):
            return _json({'error': 'Access denied — wrong tournament'})

        player = env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        ).search(
            [('id', '=', player_id), ('tournament_id', '=', tournament.id)], limit=1
        )
        if not player:
            return _json({'error': 'Player not found'})

        # Clear the binary field — Odoo will delete the ir.attachment automatically
        player.with_context(auction_skip_tournament_security=True).write({
            'payment_proof': False,
        })

        return _json({'success': True})

    @http.route([
        '/auction/projector',
        '/auction/projector/',
        '/auction/projector/<string:tournament_slug>',
        '/auction/projector/<string:tournament_slug>/',
    ], type='http', auth="none", website=False, sitemap=False)
    def projector_legacy(self, tournament_slug=None, **kw):
        """Redirect legacy URL to db+slug prefixed URL."""
        from odoo.http import db_monodb, db_list
        slug = tournament_slug or kw.get('t', '')
        # When a slug is known, resolve the DB that actually contains it so
        # multi-database servers (db_filter matching several DBs) don't redirect
        # to the wrong database, where the tournament/players don't exist.
        if slug:
            db_name = self._resolve_db_for_slug(slug)
        else:
            db_name = db_monodb(request.httprequest)
            if not db_name:
                dbs = db_list(force=True, httprequest=request.httprequest)
                db_name = dbs[0] if dbs else None
        if not db_name:
            return self._not_found()
        target = '/{}/auction/projector/{}'.format(db_name, slug + '/' if slug else '')
        return werkzeug.utils.redirect(target, 302)

    @http.route([
        '/<string:db_name>/auction/projector/',
        '/<string:db_name>/auction/projector/<string:tournament_slug>/',
    ], type='http', auth="none", website=False, sitemap=False)
    def auction_projector(self, db_name, tournament_slug=None, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            if tournament_slug:
                tournament = request.env['auction.tournament'].sudo().search(
                    [('slug', '=', tournament_slug)], limit=1)
            else:
                tournament = request.env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1)
            if tournament and not self._tournament_auction_rules_ready(tournament):
                return self._auction_rules_required_page(tournament, db_name=db_name)
            # First hit: themed splash (same pattern as Player Showcase), then load.
            if not kw.get('ready'):
                slug = tournament_slug or (tournament.slug if tournament else '')
                if slug:
                    target = '/{}/auction/projector/{}/?ready=1'.format(db_name, slug)
                else:
                    target = '/{}/auction/projector/?ready=1'.format(db_name)
                return self._showcase_loading_page(
                    target, tournament, title='Loading Players…')
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
            sport = (tournament.tournament_type or 'cricket') if tournament else 'cricket'
            mode = 'light' if theme in ('lemon', 'strawberry') else 'dark'
            company = request.env['res.company'].sudo().search([], limit=1)
            html = request.render('auction_module.projector_template', {
                'tournament': tournament,
                'theme': theme,
                'mode': mode,
                'sport': sport,
                'db_name': db_name,
                'tournament_slug': tournament_slug or (tournament.slug if tournament else ''),
                'res_company': company,
            }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/data',
    ], type='json', auth="none", website=False, sitemap=False, csrf=False)
    def auction_projector_data(self, db_name, tournament_slug, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return {'player': None}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            from datetime import datetime
            import pytz
            now_dt = datetime.now(pytz.utc).replace(tzinfo=None)
            boards = _pj_boards(tournament, db_name)
            player = None
            state_override = None
            stamp_player = None
            if (tournament and tournament.stamp_expires_at
                    and tournament.stamp_expires_at > now_dt
                    and tournament.stamp_player_id):
                stamp_player = tournament.stamp_player_id

            on_stage = request.env['auction.team.player'].browse()
            domain = [('is_on_stage', '=', True)]
            if tournament:
                domain.append(('tournament_id', '=', tournament.id))
            on_stage = request.env['auction.team.player'].sudo().search(domain, limit=1)

            # Live dice must win over a leftover on-stage row. Otherwise Roll Call
            # dice never appears on the projector after any prior player card.
            dice_state = tournament.dice_state if tournament else 'idle'
            raw_dice = int(tournament.dice_result or 0) if tournament else 0
            dice_mystery = raw_dice < 0
            lookup_sl = abs(raw_dice) if raw_dice else 0
            dice_result = 0 if dice_mystery else lookup_sl
            if tournament and lookup_sl and not dice_mystery:
                dice_player = request.env['auction.team.player'].sudo().search([
                    ('tournament_id', '=', tournament.id),
                    ('sl_no', '=', lookup_sl),
                ], limit=1)
                if (dice_player and dice_player.tier_id and dice_player.tier_id.mystery
                        and not dice_player.mystery_revealed):
                    dice_mystery = True
                    dice_result = 0
            dice_payload = {
                'state': dice_state or 'idle',
                'result': dice_result,
                'is_mystery': dice_mystery,
            }
            # Only the rolling animation blocks the player card. Once the
            # auctioneer opens a player (on stage), that must win over a leftover
            # dice "result" — otherwise the projector waits ~7s for idle.
            if dice_state == 'rolling':
                return {
                    'player': None,
                    'dice': dice_payload,
                    'progress': _pj_progress(tournament),
                    'wait_phase': _pj_wait_phase(tournament),
                    'teams': _pj_teams(tournament, db_name),
                    'recent_bids': _pj_recent_bids(tournament, db_name),
                    'top_purse': _pj_top_purse(tournament),
                    'auction_meta': _pj_auction_meta(tournament),
                    'break_time': bool(tournament and tournament.break_time_active),
                    'advertisers': _pj_advertisers(tournament, db_name),
                    'boards': boards,
                }

            # Prefer a freshly called auction player over a leftover SOLD/UNSOLD
            # stamp so projector / auctioneer / player-selector updates feel instant
            # in production (stamp otherwise blocks the next card for several seconds).
            if (on_stage and on_stage.state == 'auction'
                    and (not stamp_player or stamp_player.id != on_stage.id)):
                player = on_stage
                state_override = None
            elif stamp_player:
                player = stamp_player
                state_override = tournament.stamp_state
            elif on_stage:
                player = on_stage
            if not player:
                # Show dice result on the waiting screen until a player is opened
                if dice_state == 'result':
                    return {
                        'player': None,
                        'dice': dice_payload,
                        'progress': _pj_progress(tournament),
                        'wait_phase': _pj_wait_phase(tournament),
                        'teams': _pj_teams(tournament, db_name),
                        'recent_bids': _pj_recent_bids(tournament, db_name),
                        'top_purse': _pj_top_purse(tournament),
                        'auction_meta': _pj_auction_meta(tournament),
                        'break_time': bool(tournament and tournament.break_time_active),
                        'advertisers': _pj_advertisers(tournament, db_name),
                        'boards': boards,
                    }
                return {
                    'player': None,
                    'dice': dice_payload,
                    'progress': _pj_progress(tournament),
                    'wait_phase': _pj_wait_phase(tournament),
                    'teams': _pj_teams(tournament, db_name),
                    'recent_bids': _pj_recent_bids(tournament, db_name),
                    'top_purse': _pj_top_purse(tournament),
                    'auction_meta': _pj_auction_meta(tournament),
                    'break_time': bool(tournament and tournament.break_time_active),
                    'advertisers': _pj_advertisers(tournament, db_name),
                    'boards': boards,
                }
            photo = ''
            photo_url = ''
            if player.photo:
                photo_url = _pj_player_photo_url(db_name, player)
                # Keep tiny fallback only if URL path is unavailable to older JS
                photo = ''
            team_logo = ''
            team_logo_url = ''
            team_name = ''
            if player.assigned_team_id:
                team_name = player.assigned_team_id.name or ''
                if player.assigned_team_id.logo:
                    team_logo_url = '/%s/auction/public/image/auction.team/%d/logo' % (
                        db_name, player.assigned_team_id.id)
            sold_points = 0
            if player.state == 'sold':
                auction_line = request.env['auction.auction.player'].sudo().search(
                    [('player_id', '=', player.id)], limit=1)
                sold_points = auction_line.points if auction_line else 0
            is_mystery = bool(player.tier_id and player.tier_id.mystery)
            mystery_revealed = bool(player.mystery_revealed)
            player_payload = {
                'id': player.id,
                'sl_no': player.sl_no or '',
                'name': player.name or '',
                'role': player.role or '',
                'batting_style': player.batting_style or '',
                'bowling_style': player.bowling_style or '',
                'photo': photo,
                'photo_url': photo_url,
                'tier_name': player.tier_id.name if player.tier_id else '',
                'tier_color': player.tier_color or '#3498db',
                'base_price': player.effective_base_price or player.base_price or 0,
                'sold_points': sold_points,
                'state': state_override or player.state,
                'team_name': team_name,
                'team_logo': team_logo,
                'team_logo_url': team_logo_url,
                'is_mystery': is_mystery,
                'mystery_revealed': mystery_revealed,
            }
            player_payload.update(_football_display_payload(player))
            if is_mystery and not mystery_revealed:
                player_payload.update({
                    'name': 'Mystery Player',
                    'role': '???',
                    'sl_no': '?',
                    'photo': '',
                    'photo_url': '/auction_module/static/img/default_icon.png',
                    'tier_name': '',
                    'tier_color': '',
                    'batting_style': '',
                    'bowling_style': '',
                    'dominant_position': '???',
                    'preferred_foot': '',
                    'secondary_positions': '',
                    'age': '',
                    'height': '',
                    'weight': '',
                    'work_rate': '',
                    'p_category': '',
                    'blood_group': '',
                    'mobile': '',
                    'location': '',
                    'use_other_attributes': False,
                    'other_attributes': [],
                    'playing_styles': [],
                    'strengths': [],
                })
            leading_team_id = None
            if player.assigned_team_id and (state_override or player.state) == 'sold':
                leading_team_id = player.assigned_team_id.id
            # Live leading bid (auctioneer extension) when present
            if hasattr(player, 'current_bid') and player.current_bid:
                player_payload['current_bid'] = int(player.current_bid or 0)
                cteam = getattr(player, 'current_bid_team_id', False)
                if cteam:
                    player_payload['current_bid_team'] = {
                        'id': cteam.id,
                        'name': cteam.name or '',
                        'logo_url': (
                            '/%s/auction/public/image/auction.team/%d/logo' % (db_name, cteam.id)
                            if cteam.logo else ''
                        ),
                    }
            return {
                'player': player_payload,
                'dice': dice_payload,
                'progress': _pj_progress(tournament, current_player=player),
                'wait_phase': _pj_wait_phase(tournament),
                'teams': _pj_teams(tournament, db_name, leading_team_id=leading_team_id),
                'recent_bids': _pj_recent_bids(tournament, db_name, player=player),
                'top_purse': _pj_top_purse(tournament),
                'auction_meta': _pj_auction_meta(tournament),
                'break_time': bool(tournament and tournament.break_time_active),
                'advertisers': _pj_advertisers(tournament, db_name),
                'boards': boards,
            }

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/squad',
    ], type='json', auth='none', website=False, sitemap=False, csrf=False)
    def auction_projector_squad(self, db_name, tournament_slug, **kw):
        """All-team squad board for the projector overlay (minimal roster view)."""
        with self._with_db(db_name) as ok:
            if not ok:
                return {'sport': 'cricket', 'teams': []}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            return _pj_squad(tournament, db_name)

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/remaining',
    ], type='json', auth='none', website=False, sitemap=False, csrf=False)
    def auction_projector_remaining(self, db_name, tournament_slug, **kw):
        """Remaining auction-pool players for the projector overlay (kanban-style)."""
        with self._with_db(db_name) as ok:
            if not ok:
                return {'sport': 'cricket', 'count': 0, 'players': []}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            return _pj_remaining_players(tournament, db_name)

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/boards/close',
    ], type='json', auth='none', website=False, sitemap=False, csrf=False)
    def auction_projector_boards_close(self, db_name, tournament_slug, **kw):
        """Hide the live pool/fixture board on the projector."""
        with self._with_db(db_name) as ok:
            if not ok:
                return {'ok': False}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            if tournament:
                tournament.sudo().write({
                    'projector_board_mode': 'idle',
                    'projector_board_reveal_until': False,
                })
            return {'ok': True}

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/boards/show',
    ], type='json', auth='none', website=False, sitemap=False, csrf=False)
    def auction_projector_boards_show(self, db_name, tournament_slug, mode='pools', **kw):
        """Manually show saved pools or fixtures on the projector."""
        with self._with_db(db_name) as ok:
            if not ok:
                return {'ok': False}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return {'ok': False}
            mode = mode if mode in ('pools', 'fixtures') else 'pools'
            if mode == 'pools' and not tournament.pool_draw_json:
                return {'ok': False, 'error': 'No pool draw saved'}
            if mode == 'fixtures' and not tournament.fixture_schedule_json:
                return {'ok': False, 'error': 'No fixture saved'}
            tournament.sudo().write({
                'projector_board_mode': mode,
                'projector_board_reveal_until': False,
            })
            return {'ok': True, 'boards': _pj_boards(tournament, db_name)}

    def _showcase_loading_page(self, redirect_url, tournament=None, title=None):
        """Lightweight splash before Player Console / Projector loads.

        Must render eagerly (lazy=False): callers often use this inside
        ``_with_db``, which closes the cursor on exit — deferred QWeb would
        then hit ``Unable to use a closed cursor`` when reading tournament.
        """
        theme = 'lemon'
        if tournament:
            theme = tournament.player_display_template or 'lemon'
        html = request.render('auction_module.auction_showcase_loading', {
            'redirect_url': redirect_url,
            'tournament': tournament,
            'theme': theme,
            'loading_title': title or 'Loading Player Console…',
        }, lazy=False)
        return request.make_response(
            html, [('Content-Type', 'text/html; charset=utf-8')]
        )

    def _showcase_target_url(self, tournament):
        """Resolve Player Console URL for the tournament algorithm."""
        if not tournament:
            return '/auction/display_auction'
        db_name = request.env.cr.dbname
        if tournament.slug:
            if tournament.player_appearance_algorithm == 'linear':
                return '/{}/auction/player_selector/{}/'.format(db_name, tournament.slug)
            return '/{}/auction/display_auction/{}/'.format(db_name, tournament.slug)
        if tournament.player_appearance_algorithm == 'linear':
            return '/auction/player_selector'
        return '/auction/display_auction'

    @http.route('/auction/showcase', type='http', auth='user', website=True)
    def auction_showcase(self, **kw):
        """Show a brief loading splash, then open the Player Console."""
        tournament = self._resolve_tournament()
        if tournament and not self._tournament_auction_rules_ready(tournament):
            return self._auction_rules_required_page(tournament)
        if tournament:
            tournament.action_dismiss_projector_board()
        target = self._showcase_target_url(tournament)
        return self._showcase_loading_page(target, tournament)

    @http.route('/auction/status/data', type='http', auth='public', website=True, csrf=False)
    def auction_status_data(self, last_id=0, **kw):

        last_id = int(last_id or 0)

        records = request.env['auction.history'].sudo().search(
            [('id', '>', last_id)],
            order='id asc',
            limit=20
        )

        data = []
        for rec in records:
            data.append({
                'id': int(rec.id),
                'message': str(rec.message or ''),
                'image_url': f"/web/image/auction.history/{rec.id}/player_photo",
            })

        payload = {
            'records': data,
            'last_id': int(data[-1]['id']) if data else last_id
        }

        return request.make_response(
            json.dumps(payload),
            headers=[('Content-Type', 'application/json')]
        )

    # ─────────────────────────────────────────────────────────────────
    #  PUBLIC LIVE AUCTION BOARD
    # ─────────────────────────────────────────────────────────────────

    # Whitelist of models and fields that public users may fetch images from.
    _PUBLIC_IMAGE_FIELDS = {
        'auction.team.player': ['photo'],
        'auction.team':        ['logo'],
        'auction.tournament':  ['logo', 'pool_draw_snapshot', 'fixture_schedule_snapshot'],
        'auction.history':     ['player_photo'],
        'auction.advertiser':  ['image'],
        'res.company':         ['favicon'],
        'auction.champ.jersey.team': ['team_logo', 'sponsor_logo', 'jersey_design'],
    }

    @staticmethod
    def _image_mimetype(image_bytes):
        """Detect the image mimetype from its magic bytes.

        The stored images are usually JPEG but were previously served as
        image/png. A CDN/reverse-proxy in front of the production server can
        reject or mis-cache a response whose declared Content-Type does not
        match its actual bytes, which shows up as broken images in the browser.
        """
        if image_bytes[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return 'image/webp'
        if image_bytes[:2] == b'BM':
            return 'image/bmp'
        # Windows ICO (common for company favicon)
        if image_bytes[:4] == b'\x00\x00\x01\x00':
            return 'image/x-icon'
        return 'image/jpeg'

    def _public_image_bytes(self, binary, model, field, **kw):
        """Decode binary image; optionally downscale player photos for projector (sz=pj)."""
        if (
            model == 'auction.team.player'
            and field == 'photo'
            and (kw.get('sz') or '').lower() == 'pj'
            and binary
        ):
            try:
                binary = image_process(
                    binary, size=(720, 1000), quality=82, output_format='JPEG',
                ) or binary
            except Exception:
                _logger.debug('public image sz=pj resize failed', exc_info=True)
        return base64.b64decode(binary)

    def _public_image_response(self, image_bytes):
        return request.make_response(image_bytes, headers=[
            ('Content-Type', self._image_mimetype(image_bytes)),
            # Long browser/CDN cache — projector URLs include ?v=write_date for busting
            ('Cache-Control', 'public, max-age=86400, stale-while-revalidate=604800'),
        ])

    @http.route('/auction/public/image/<string:model>/<int:record_id>/<string:field>',
                type='http', auth='public', website=False, csrf=False)
    def auction_public_image(self, model, record_id, field, **kw):
        """Serve binary images to unauthenticated users for the public live-board."""
        allowed_fields = self._PUBLIC_IMAGE_FIELDS.get(model)
        if not allowed_fields or field not in allowed_fields:
            return request.not_found()

        record = request.env[model].sudo().browse(record_id)
        if not record.exists():
            return request.not_found()

        binary = getattr(record, field, None)
        if not binary:
            return request.not_found()

        return self._public_image_response(
            self._public_image_bytes(binary, model, field, **kw))

    @http.route('/<string:db_name>/auction/public/image/<string:model>/<int:record_id>/<string:field>',
                type='http', auth='none', website=False, csrf=False)
    def auction_public_image_db(self, db_name, model, record_id, field, **kw):
        """Same as auction_public_image but with an explicit db_name in the URL.

        Used by the public live-board in multi-database setups where no session
        exists and Odoo cannot infer the database automatically.
        """
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            allowed_fields = self._PUBLIC_IMAGE_FIELDS.get(model)
            if not allowed_fields or field not in allowed_fields:
                return self._not_found()

            record = request.env[model].sudo().browse(record_id)
            if not record.exists():
                return self._not_found()

            binary = getattr(record, field, None)
            if not binary:
                return self._not_found()

            image_bytes = self._public_image_bytes(binary, model, field, **kw)
        return self._public_image_response(image_bytes)

    @http.route('/auction/live-board', type='http', auth='none', website=False)
    def auction_live_board_legacy(self, **kw):
        """Redirect legacy /auction/live-board URL to the db-slug-based URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('active', '=', True)], limit=1
            )
            if tournament and tournament.slug:
                return werkzeug.utils.redirect('/{}/{}/auction/live-board'.format(db_name, tournament.slug), 301)
        return self._not_found()

    @http.route('/<string:tournament_slug>/auction/live-board', type='http', auth='none', website=False)
    def auction_live_board_slug_legacy(self, tournament_slug, **kw):
        """Redirect old slug-only URL to db-prefixed URL."""
        db_name = self._resolve_db_for_slug(tournament_slug)
        if not db_name:
            return self._not_found()
        return werkzeug.utils.redirect('/{}/{}/auction/live-board'.format(db_name, tournament_slug), 301)

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/live-board',
                type='http', auth='none', website=False, methods=['GET', 'POST'], csrf=False)
    def auction_live_board(self, db_name, tournament_slug, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            env = request.env
            tournament = env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )

            if not tournament:
                return self._not_found()

            theme = tournament.player_display_template or 'vanilla'

            has_rules = env['auction.auction'].sudo().search_count(
                [('tournament_id', '=', tournament.id)]
            ) > 0
            has_players = env['auction.team.player'].sudo().search_count([]) > 0
            auction_ready = has_rules and has_players

            if not auction_ready:
                html = request.render('auction_module.welcome_message_template', {
                    'tournament': tournament,
                    'theme': theme,
                    'db_name': db_name,
                }, lazy=False)
            elif not tournament.live_board_active:
                html = request.render('auction_module.live_board_offline_template', {
                    'tournament': tournament,
                    'theme': theme,
                    'db_name': db_name,
                }, lazy=False)
            else:
                # Optional Tournament Code gate (see live_board_code_protected).
                # When protected: unlock once, then remember via session + cookie.
                if not self._live_board_access_granted(tournament):
                    entered = (kw.get('tournament_code') or '').strip()
                    if request.httprequest.method == 'POST':
                        if not (tournament.tournament_code or '').strip():
                            return self._render_live_board_unlock(
                                tournament, db_name, tournament_slug, theme=theme,
                                error='This tournament has no access code yet. Ask the organiser to open the tournament form and share the Tournament Code.',
                                entered_code=entered,
                            )
                        if self._live_board_try_unlock(tournament, entered):
                            return self._live_board_unlock_redirect(
                                db_name, tournament_slug, tournament,
                            )
                        return self._render_live_board_unlock(
                            tournament, db_name, tournament_slug, theme=theme,
                            error='Invalid tournament code. Please check with the organiser.',
                            entered_code=entered,
                        )
                    return self._render_live_board_unlock(
                        tournament, db_name, tournament_slug, theme=theme,
                    )

                html = request.render('auction_module.public_live_board_template', {
                    'tournament': tournament,
                    'theme': theme,
                    'db_name': db_name,
                    'tournament_slug': tournament_slug,
                }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/auction/live-board/data', type='http', auth='none', website=False, csrf=False)
    def auction_live_board_data_legacy(self, **kw):
        """Redirect legacy /auction/live-board/data URL to the db-slug-based URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('active', '=', True)], limit=1
            )
            if tournament and tournament.slug:
                return werkzeug.utils.redirect('/{}/{}/auction/live-board/data'.format(db_name, tournament.slug), 301)
        return self._not_found()

    @http.route('/<string:tournament_slug>/auction/live-board/data', type='http', auth='none', website=False, csrf=False)
    def auction_live_board_data_slug_legacy(self, tournament_slug, **kw):
        """Redirect old slug-only URL to db-prefixed URL."""
        db_name = self._resolve_db_for_slug(tournament_slug)
        if not db_name:
            return self._not_found()
        return werkzeug.utils.redirect('/{}/{}/auction/live-board/data'.format(db_name, tournament_slug), 301)

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/live-board/data', type='http', auth='none', website=False, csrf=False)
    def auction_live_board_data(self, db_name, tournament_slug, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return request.make_response(
                    json.dumps({'error': 'unknown database'}),
                    headers=[('Content-Type', 'application/json')]
                )
            env = request.env
            tournament = env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )

            if not tournament:
                return request.make_response(
                    json.dumps({'error': 'tournament not found'}),
                    headers=[('Content-Type', 'application/json')]
                )

            if not tournament.live_board_active:
                return request.make_response(
                    json.dumps({'live_board_active': False}),
                    headers=[('Content-Type', 'application/json')]
                )

            if not self._live_board_access_granted(tournament):
                return request.make_response(
                    json.dumps({
                        'error': 'locked',
                        'message': 'Tournament code required',
                        'live_board_active': True,
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=403,
                )

            def pub_img(model, record_id, field):
                return '/%s/auction/public/image/%s/%d/%s' % (db_name, model, record_id, field)

            result = {
                'tournament': {},
                'current_player': None,
                'sold_info': None,
                'recent_history': [],
                'top_players': [],
                'teams': [],
                'theme': 'vanilla',
                'no_auction': True,
                'break_time': False,
                'advertisers': [],
                'stats': {},
                'wait_phase': {},
            }

            if tournament:
                result['theme'] = tournament.player_display_template or 'vanilla'
                result['break_time'] = tournament.break_time_active
                result['advertisers'] = [
                    {
                        'id': ad.id,
                        'name': ad.name or '',
                        'image_url': pub_img('auction.advertiser', ad.id, 'image'),
                    }
                    for ad in tournament.advertiser_ids if ad.image
                ]
                result['tournament'] = {
                    'name': tournament.name or '',
                    'description': tournament.description or '',
                    'logo_url': pub_img('auction.tournament', tournament.id, 'logo') if tournament.logo else '',
                    'tournament_type': tournament.tournament_type or 'cricket',
                }
                result['tournament_type'] = tournament.tournament_type or 'cricket'

            # ── Stamp-first: check if tournament has an active sold/unsold stamp ──
            stamp_player = None
            stamp_state_val = None
            now_dt = fields.Datetime.now()
            if tournament.stamp_expires_at and tournament.stamp_expires_at > now_dt and tournament.stamp_player_id:
                stamp_player = tournament.stamp_player_id
                stamp_state_val = tournament.stamp_state

            # ── Current player on stage (normal display) ──
            current_player = env['auction.team.player'].sudo().search([
                ('is_on_stage', '=', True),
                ('tournament_id', '=', tournament.id),
            ], limit=1)

            # If stamp is active use the stamp player as the displayed player
            # so the live board shows SOLD/UNSOLD even after is_on_stage
            # has moved on to the next player.
            if stamp_player:
                current_player = stamp_player

            if current_player:
                result['no_auction'] = False

                # Base price: check auctions for this tournament
                base_price = 0
                auctions_all = env['auction.auction'].sudo().search(
                    [('tournament_id', '=', tournament.id)]
                )
                for auc in auctions_all:
                    base = auc.base_point or 0
                    if current_player.tier_id and auc.tier_limit_ids:
                        tl = auc.tier_limit_ids.filtered(
                            lambda l: l.tier_id.id == current_player.tier_id.id
                        )
                        if tl and tl[0].base_point > 0:
                            base = tl[0].base_point
                    if base > base_price:
                        base_price = base

                result['current_player'] = {
                    'id': current_player.id,
                    'name': current_player.name or '',
                    'photo_url': pub_img('auction.team.player', current_player.id, 'photo') if current_player.photo else '',
                    'role': current_player.role or '',
                    'tier_name': current_player.tier_id.name if current_player.tier_id else '',
                    'tier_color': current_player.tier_color or '#2252b5',
                    'state': current_player.state,
                    'sl_no': current_player.sl_no or 0,
                    'icon_player': current_player.icon_player,
                    'base_price': base_price,
                    'batting_style': current_player.batting_style or '',
                    'bowling_style': current_player.bowling_style or '',
                    'is_mystery': bool(current_player.tier_id and current_player.tier_id.mystery),
                    'mystery_revealed': bool(current_player.mystery_revealed),
                }
                result['current_player'].update(_football_display_payload(current_player))

                # Mystery players stay redacted on the live board until revealed
                # on the auction stage after the sale.
                if (result['current_player']['is_mystery']
                        and not result['current_player']['mystery_revealed']):
                    result['current_player'].update({
                        'name': 'Mystery Player?',
                        'photo_url': '/auction_module/static/img/default_icon.png',
                        'role': '',
                        'tier_name': '',
                        'sl_no': 0,
                        'icon_player': False,
                        'batting_style': '',
                        'bowling_style': '',
                        'dominant_position': '',
                        'preferred_foot': '',
                        'secondary_positions': '',
                        'age': '',
                        'use_other_attributes': False,
                        'other_attributes': [],
                        'playing_styles': [],
                        'strengths': [],
                    })

                # ── If sold, get final points from auction line ──
                if current_player.state == 'sold' and current_player.assigned_team_id:
                    auc_line = env['auction.auction.player'].sudo().search(
                        [('player_id', '=', current_player.id)], limit=1
                    )
                    team = current_player.assigned_team_id
                    result['sold_info'] = {
                        'team_name': team.name or '',
                        'team_logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                        'amount': auc_line.points if auc_line else 0,
                    }

            # ── Recent history (last 5 transactions) ──
            history = env['auction.history'].sudo().search(
                [('tournament_id', '=', tournament.id)], order='create_date desc', limit=5
            )
            # Names that must stay hidden until Reveal (covers older history rows
            # that were written with the real name before this fix).
            hidden_mystery = env['auction.team.player'].sudo().search([
                ('tournament_id', '=', tournament.id),
                ('tier_id.mystery', '=', True),
                ('mystery_revealed', '=', False),
                ('state', '=', 'sold'),
            ])
            hidden_names = {p.name for p in hidden_mystery if p.name}

            recent_history = []
            for rec in history:
                msg = rec.message or ''
                photo_url = pub_img('auction.history', rec.id, 'player_photo') if rec.player_photo else ''
                p = rec.player_id
                must_hide = (
                    (p and p.tier_id and p.tier_id.mystery and not p.mystery_revealed)
                    or any(n in msg for n in hidden_names)
                )
                if must_hide:
                    for n in hidden_names:
                        if n and n in msg:
                            msg = msg.replace(n, '???', 1)
                    if p and p.name and p.name in msg:
                        msg = msg.replace(p.name, '???', 1)
                    photo_url = '/auction_module/static/img/default_icon.png'
                recent_history.append({
                    'message': msg,
                    'team_logo_url': pub_img('auction.team', rec.team_id.id, 'logo') if rec.team_id and rec.team_id.logo else '',
                    'player_photo_url': photo_url,
                    'timestamp': rec.create_date.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata')).strftime('%I:%M %p') if rec.create_date else '',
                })
            result['recent_history'] = recent_history

            # ── Top 5 most expensive sold players (MVP board) ──
            top_sold = env['auction.auction.player'].sudo().search(
                [('auction_id.tournament_id', '=', tournament.id)], order='points desc', limit=5
            )
            top_players = []
            for idx, rec in enumerate(top_sold):
                p = rec.player_id
                name = p.name or '' if p else ''
                photo = pub_img('auction.team.player', p.id, 'photo') if p and p.photo else ''
                role = p.role or '' if p else ''
                if p and p.tier_id and p.tier_id.mystery and not p.mystery_revealed:
                    name = '???'
                    photo = '/auction_module/static/img/default_icon.png'
                    role = '???'
                top_players.append({
                    'rank': idx + 1,
                    'player_name': name,
                    'player_photo_url': photo,
                    'role': role,
                    'team_name': rec.auction_id.team_id.name if rec.auction_id and rec.auction_id.team_id else '',
                    'team_logo_url': pub_img('auction.team', rec.auction_id.team_id.id, 'logo') if rec.auction_id and rec.auction_id.team_id and rec.auction_id.team_id.logo else '',
                    'points': rec.points,
                })
            result['top_players'] = top_players

            # ── Teams (from auctions in this tournament) ──
            is_football = (tournament.tournament_type == 'football')
            auctions = env['auction.auction'].sudo().search(
                [('tournament_id', '=', tournament.id)]
            )
            for auc in auctions:
                team = auc.team_id
                if team:
                    players_payload = []
                    for line in auc.player_ids:
                        if not line.player_id:
                            continue
                        p = line.player_id
                        pos_code = ''
                        pos_name = ''
                        if is_football and p.dominant_position_id:
                            pos_code = (p.dominant_position_id.code or '').strip().upper()
                            pos_name = p.dominant_position_id.name or ''
                            if not pos_code and pos_name:
                                # Derive abbreviation from name words when code is empty
                                parts = [w for w in pos_name.replace('-', ' ').split() if w]
                                pos_code = ''.join(w[0] for w in parts).upper()[:3]
                        entry = {
                            'name': p.name or '',
                            'photo_url': pub_img('auction.team.player', p.id, 'photo')
                                         if p.photo else '',
                            'role': p.role or '',
                            'position_code': pos_code,
                            'position_name': pos_name,
                            'points': line.points,
                        }
                        # Keep mystery buys hidden in team lists until revealed
                        if (p.tier_id and p.tier_id.mystery and not p.mystery_revealed):
                            entry.update({
                                'name': '???',
                                'photo_url': '/auction_module/static/img/default_icon.png',
                                'role': '???',
                                'position_code': '?',
                                'position_name': '???',
                            })
                        players_payload.append(entry)
                    result['teams'].append({
                        'id': team.id,
                        'name': team.name or '',
                        'logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                        'remaining_points': auc.remaining_points,
                        'manager': team.manager or '',
                        'players': players_payload,
                    })

            # ── Player state counts for this tournament (stats block) ──
            Player = env['auction.team.player'].sudo()
            tdom = [('tournament_id', '=', tournament.id)]
            result['stats'] = {
                'in_auction': Player.search_count(tdom + [('state', '=', 'auction')]),
                'sold':       Player.search_count(tdom + [('state', '=', 'sold')]),
                'unsold':     Player.search_count(tdom + [('state', '=', 'unsold')]),
                'total':      Player.search_count(tdom),
            }

            # Same complete-phase logic as projector, with viewer-facing copy
            result['wait_phase'] = _pj_wait_phase(tournament, audience='viewers')

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        )

    # ── Auction Dashboard ─────────────────────────────────────────────────────

    @http.route('/auction/dashboard', type='http', auth='user', website=True)
    def auction_dashboard(self, **kw):
        tournament = self._resolve_tournament()
        payment_tracker_url = ''
        if tournament and tournament.slug:
            db_name = request.env.cr.dbname
            payment_tracker_url = '/{}/{}/auction/payment-marker'.format(db_name, tournament.slug)
        return request.render('auction_module.auction_dashboard_template', {
            'tournament': tournament,
            'payment_tracker_url': payment_tracker_url,
        })

    @http.route('/auction/dashboard/data', type='http', auth='user', website=False, csrf=False)
    def auction_dashboard_data(self, **kw):
        env = request.env
        tournament = self._resolve_tournament()

        # Always count ALL players by state (not filtered by tournament).
        # This ensures the registration pie chart always shows real data,
        # even if some players were created without a tournament link.
        draft_count   = env['auction.team.player'].sudo().search_count([('state', '=', 'draft')])
        auction_count = env['auction.team.player'].sudo().search_count([('state', '=', 'auction')])
        sold_count    = env['auction.team.player'].sudo().search_count([('state', '=', 'sold')])
        unsold_count  = env['auction.team.player'].sudo().search_count([('state', '=', 'unsold')])

        def pub_img(model, record_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

        auc_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = env['auction.auction'].sudo().search(auc_domain)

        # Look up the on-stage player once so tier-based max_call caps are applied.
        on_stage = env['auction.team.player'].sudo().search(
            [('is_on_stage', '=', True)], limit=1
        )
        player_on_stage = on_stage if on_stage else None

        teams_data = []
        for auc in auctions:
            team = auc.team_id
            if not team:
                continue

            top_player_line = env['auction.auction.player'].sudo().search(
                [('auction_id', '=', auc.id)],
                order='points desc',
                limit=1,
            )

            top_player_info = None
            if top_player_line:
                player = top_player_line.player_id
                top_player_info = {
                    'name': player.name or '',
                    'photo_url': pub_img('auction.team.player', player.id, 'photo') if player.photo else '',
                    'points': top_player_line.points,
                    'role': player.role or '',
                }

            teams_data.append({
                'id': team.id,
                'name': team.name or '',
                'manager': team.manager or '',
                'logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                'total_points': auc.total_point,
                'remaining_points': auc.remaining_points,
                'remaining_players': auc.remaining_players_count,
                'max_players': auc.max_players,
                'max_call': auc.get_max_bid_for_team(auc, player_on_stage),
                'players_bought': len(auc.player_ids),
                'top_player': top_player_info,
            })

        result = {
            'player_counts': {
                'draft':   draft_count,
                'auction': auction_count,
                'sold':    sold_count,
                'unsold':  unsold_count,
            },
            'teams': teams_data,
            'tournament': {
                'name':        tournament.name        if tournament else '',
                'description': tournament.description if tournament else '',
                'logo_url':    pub_img('auction.tournament', tournament.id, 'logo') if tournament and tournament.logo else '',
            },
        }

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        )

    # ── Player Detail Dashboard ───────────────────────────────────────────────

    @http.route('/auction/player-dashboard/data', type='http', auth='user', website=False, csrf=False)
    def player_dashboard_data(self, **kw):
        env = request.env
        Player    = env['auction.team.player'].sudo()
        AucPlayer = env['auction.auction.player'].sudo()

        def pub_img(model, rec_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, rec_id, field)

        # ── Tournament scope (same dropdown rules as Payment Tracker) ─────────
        tournament_choices, show_tournament_filter, _is_saas = (
            self._pm_tournament_filter_meta()
        )
        user_tournament = self._resolve_pd_tournament(
            tournament_id=kw.get('tournament_id'),
        )

        if user_tournament:
            t_domain = [('tournament_id', '=', user_tournament.id)]
        else:
            # No accessible tournament → show nothing (do not leak all data)
            t_domain = [('id', '=', False)]

        # ── State counts ──────────────────────────────────────────────────────
        states = ['draft', 'auction', 'sold', 'unsold']
        state_counts = {s: Player.search_count(t_domain + [('state', '=', s)]) for s in states}
        total = sum(state_counts.values())

        tournament_type = (user_tournament.tournament_type if user_tournament else 'cricket') or 'cricket'
        is_football = tournament_type == 'football'

        # ── Last 10 draft players ─────────────────────────────────────────────
        last_draft = Player.search(t_domain + [('state', '=', 'draft')], order='create_date desc', limit=10)
        draft_players = []
        for p in last_draft:
            if is_football:
                display_role = (p.dominant_position_id.name if p.dominant_position_id else '') or (p.role or '')
            else:
                display_role = p.role or ''
            draft_players.append({
                'name':        p.name or '',
                'role':        display_role,
                'tier':        p.tier_id.name if p.tier_id else '',
                'base_price':  p.base_price or 0,
                'photo_url':   pub_img('auction.team.player', p.id, 'photo') if p.photo else '',
                'create_date': p.create_date.strftime('%d %b %Y') if p.create_date else '',
            })

        # ── Last 5 days daily registrations ──────────────────────────────────
        tz = pytz.timezone('Asia/Kolkata')
        today_local = datetime.now(tz).date()
        daily = []
        for i in range(4, -1, -1):
            day = today_local - timedelta(days=i)
            day_start_utc = tz.localize(datetime(day.year, day.month, day.day, 0, 0, 0)).astimezone(pytz.utc).replace(tzinfo=None)
            day_end_utc   = tz.localize(datetime(day.year, day.month, day.day, 23, 59, 59)).astimezone(pytz.utc).replace(tzinfo=None)
            count = Player.search_count(t_domain + [
                ('create_date', '>=', fields.Datetime.to_string(day_start_utc)),
                ('create_date', '<=', fields.Datetime.to_string(day_end_utc)),
            ])
            daily.append({'label': day.strftime('%d %b'), 'count': count})

        # ── Role / Playing-position distribution ──────────────────────────────
        all_players = Player.search(t_domain)
        role_counts = {}
        position_counts = {}
        for p in all_players:
            role = (p.role or 'Unknown').strip() or 'Unknown'
            role_counts[role] = role_counts.get(role, 0) + 1
            if is_football:
                pos = (p.dominant_position_id.name if p.dominant_position_id else 'Unknown').strip() or 'Unknown'
                position_counts[pos] = position_counts.get(pos, 0) + 1
        roles = [{'label': k, 'count': v} for k, v in sorted(role_counts.items(), key=lambda x: -x[1])]
        positions = [{'label': k, 'count': v} for k, v in sorted(position_counts.items(), key=lambda x: -x[1])]

        # ── Tier distribution ─────────────────────────────────────────────────
        tier_counts = {}
        for p in all_players:
            tier = p.tier_id.name if p.tier_id else 'No Tier'
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        tiers = [{'label': k, 'count': v} for k, v in sorted(tier_counts.items(), key=lambda x: -x[1])]

        # ── Icon players count ────────────────────────────────────────────────
        icon_count = Player.search_count(t_domain + [('icon_player', '=', True)])

        # ── Amount paid / unpaid ──────────────────────────────────────────────
        paid_count   = Player.search_count(t_domain + [('amount_paid', '=', True)])
        unpaid_count = Player.search_count(t_domain + [('amount_paid', '=', False)])

        # ── Players per team (sold players grouped by team) ───────────────────
        team_counts = {}
        for p in all_players:
            if p.assigned_team_id:
                tname = p.assigned_team_id.name or 'Unknown'
                team_counts[tname] = team_counts.get(tname, 0) + 1
        team_player_counts = [{'label': k, 'count': v}
                               for k, v in sorted(team_counts.items(), key=lambda x: -x[1])]

        # ── Icon / Key players with team assignment ───────────────────────────
        icon_players = Player.search(t_domain + [('icon_player', '=', True)], order='assigned_team_id, name')
        icon_list = []
        for p in icon_players:
            auc_line = AucPlayer.search([('player_id', '=', p.id)], order='points desc', limit=1)
            if is_football:
                display_role = (p.dominant_position_id.name if p.dominant_position_id else '') or (p.role or '')
            else:
                display_role = p.role or ''
            icon_list.append({
                'name':      p.name or '',
                'role':      display_role,
                'tier':      p.tier_id.name if p.tier_id else '',
                'team':      p.assigned_team_id.name if p.assigned_team_id else 'Unassigned',
                'team_logo': pub_img('auction.team', p.assigned_team_id.id, 'logo')
                             if p.assigned_team_id and p.assigned_team_id.logo else '',
                'points':    auc_line.points if auc_line else 0,
                'photo_url': pub_img('auction.team.player', p.id, 'photo') if p.photo else '',
            })

        # ── Resolve view IDs ─────────────────────────────────────────────────
        def _ref(xml_id):
            try:
                return request.env.ref('auction_module.' + xml_id).id
            except Exception:
                return False

        result = {
            'total':             total,
            'state_counts':      state_counts,
            'icon_count':        icon_count,
            'paid_count':        paid_count,
            'unpaid_count':      unpaid_count,
            'draft_players':     draft_players,
            'daily':             daily,
            'roles':             roles,
            'positions':         positions,
            'tournament_type':   tournament_type,
            'tiers':             tiers,
            'team_player_counts': team_player_counts,
            'icon_players':      icon_list,
            'tournament_id':     user_tournament.id if user_tournament else None,
            'tournament_name':   user_tournament.name if user_tournament else '',
            'tournament_logo':   (
                pub_img('auction.tournament', user_tournament.id, 'logo')
                if user_tournament and user_tournament.logo else ''
            ),
            'tournaments': tournament_choices,
            'show_tournament_filter': show_tournament_filter,
            'view_ids': {
                'kanban': _ref('view_auction_team_player_kanban'),
                'list':   _ref('view_auction_team_player_tree'),
            },
        }
        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        )

    def _resolve_pd_tournament(self, tournament_id=None):
        """Resolve the Player Dashboard tournament (mirrors Payment Tracker rules)."""
        env = request.env
        user = env.user.sudo()
        is_admin = user.has_group('auction_module.group_auction_group_admin')

        if tournament_id not in (None, False, '', 'null', 'undefined'):
            try:
                tid = int(tournament_id)
            except (TypeError, ValueError):
                tid = False
            if tid:
                tournament = env['auction.tournament'].sudo().browse(tid)
                if tournament.exists() and self._pm_user_can_access_tournament(tournament):
                    return tournament

        tournament = False
        get_working = getattr(user, 'get_working_tournament', None)
        if callable(get_working):
            try:
                tournament = get_working()
            except Exception:
                tournament = False
        if not tournament:
            tournament = user.tournament_id or user.tournament_ids[:1]
        if not tournament and is_admin:
            tournament = env['auction.tournament'].sudo().search(
                [('active', '=', True)], order='name asc, id asc', limit=1,
            )
        if tournament and not self._pm_user_can_access_tournament(tournament):
            return env['auction.tournament']
        return tournament

    # ── Squad Poster (franchise 2:3 · 1024×1536) ──────────────────────────────

    SP_CANVAS_W = 1024
    SP_CANVAS_H = 1536

    def _sp_b64_uri(self, binary, mime='image/jpeg', size=None, quality=95):
        """Binary field → data URI; optional resize for crisp poster cards."""
        if not binary:
            return ''
        raw = binary
        try:
            if size:
                processed = image_process(raw, size=size, quality=quality)
                if processed:
                    raw = processed
        except Exception:
            pass
        if isinstance(raw, bytes):
            raw = raw.decode('ascii')
        return 'data:%s;base64,%s' % (mime, raw)

    def _sp_logo_uri(self, binary, size=(360, 360)):
        """
        Team/tournament logo → PNG on a transparent square.

        Conservative plate removal only: edge-flood when 3+ corners are a solid
        white/black plate. Never globally deletes white (preserves white logo art).
        If unsure, keeps the original mark intact.
        """
        if not binary:
            return ''
        from io import BytesIO
        from PIL import Image
        try:
            raw = binary
            if isinstance(raw, str):
                raw = base64.b64decode(raw)
            elif isinstance(raw, bytes):
                try:
                    Image.open(BytesIO(raw)).verify()
                    # verify() exhausts; reopen below
                except Exception:
                    try:
                        raw = base64.b64decode(raw)
                    except Exception:
                        pass

            src = Image.open(BytesIO(raw if isinstance(raw, (bytes, bytearray)) else base64.b64decode(binary)))
            try:
                from PIL import ImageOps
                src = ImageOps.exif_transpose(src)
            except Exception:
                pass

            rgba = src.convert('RGBA')
            tw, th = size

            def _fit(img, use_mask=True):
                img = img.copy()
                img.thumbnail((tw - 8, th - 8), Image.LANCZOS)
                canvas = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
                ow, oh = img.size
                if use_mask:
                    canvas.paste(img, ((tw - ow) // 2, (th - oh) // 2), img)
                else:
                    canvas.paste(img, ((tw - ow) // 2, (th - oh) // 2))
                buf = BytesIO()
                canvas.save(buf, format='PNG', optimize=True)
                return 'data:image/png;base64,%s' % base64.b64encode(buf.getvalue()).decode('ascii')

            # Already transparent artwork — never re-key
            if 'A' in src.getbands():
                a0, _a1 = rgba.split()[-1].getextrema()
                if a0 < 250:
                    return _fit(rgba, use_mask=True)

            w, h = rgba.size
            if w < 8 or h < 8:
                return _fit(rgba, use_mask=False)

            pix = rgba.load()

            def _is_white(r, g, b, a):
                return a >= 20 and r >= 242 and g >= 242 and b >= 242

            def _is_black(r, g, b, a):
                return a >= 20 and r <= 14 and g <= 14 and b <= 14

            corners = [
                pix[2, 2], pix[w - 3, 2], pix[2, h - 3], pix[w - 3, h - 3]
            ]
            white_n = sum(1 for c in corners if _is_white(c[0], c[1], c[2], c[3]))
            black_n = sum(1 for c in corners if _is_black(c[0], c[1], c[2], c[3]))
            mode = 'white' if white_n >= 3 else ('black' if black_n >= 3 else None)

            if not mode:
                # No clear plate — keep logo as-is (white details preserved)
                return _fit(rgba, use_mask=False)

            match = _is_white if mode == 'white' else _is_black
            work = rgba.copy()
            wp = work.load()
            visited = [[False] * w for _ in range(h)]
            stack = []
            for x in range(w):
                stack.append((x, 0))
                stack.append((x, h - 1))
            for y in range(h):
                stack.append((0, y))
                stack.append((w - 1, y))
            cleared = 0
            while stack:
                x, y = stack.pop()
                if x < 0 or y < 0 or x >= w or y >= h or visited[y][x]:
                    continue
                visited[y][x] = True
                r, g, b, a = wp[x, y]
                if not match(r, g, b, a):
                    continue
                wp[x, y] = (r, g, b, 0)
                cleared += 1
                stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

            total = float(w * h)
            bbox = work.split()[-1].getbbox()
            # Require a real plate removal that still leaves a solid mark
            if not bbox or cleared < total * 0.10 or cleared > total * 0.70:
                return _fit(rgba, use_mask=False)

            return _fit(work.crop(bbox), use_mask=True)
        except Exception:
            _logger.exception('Squad poster logo clean failed; falling back')
            return self._sp_b64_uri(binary, mime='image/png', size=size, quality=95)

    def _sp_open_image(self, binary):
        """Decode an Odoo binary/base64 field into a PIL RGB image."""
        from io import BytesIO
        from PIL import Image
        if not binary:
            return None
        raw = binary
        if isinstance(raw, str):
            raw = base64.b64decode(raw)
        elif isinstance(raw, bytes):
            # Odoo may store raw bytes or base64 bytes
            try:
                return Image.open(BytesIO(raw)).convert('RGB')
            except Exception:
                try:
                    raw = base64.b64decode(raw)
                except Exception:
                    return None
        try:
            return Image.open(BytesIO(raw)).convert('RGB')
        except Exception:
            return None

    def _sp_detect_face_box(self, im):
        """
        Best-effort face box (x, y, w, h) in image pixels.
        Prefer OpenCV Haar when available; otherwise YCbCr skin-blob + head bias.
        """
        W, H = im.size
        # 1) OpenCV Haar (frontal + alt) — strongest when package is installed
        cv_box = self._sp_detect_face_opencv(im)
        if cv_box:
            return cv_box

        # 2) YCbCr skin blob in upper torso (works for Indian skin tones without cv2)
        skin_box = self._sp_detect_face_skin(im)
        if skin_box:
            return skin_box

        # 3) Soft center-of-mass skin heuristic
        cx, cy, conf = self._sp_estimate_face_center(im, with_confidence=True)
        if conf >= 0.008:
            fw = int(min(W, H) * (0.38 if H > W * 1.25 else 0.46))
            fh = int(fw * 1.15)  # face boxes are slightly taller than wide
            x = int(cx * W - fw / 2.0)
            y = int(cy * H - fh * 0.42)
            x = max(0, min(x, W - fw))
            y = max(0, min(y, H - fh))
            return x, y, max(24, fw), max(24, fh)

        # 4) Portrait fallback — upper-center (typical jersey / selfie / full-body head)
        fw = int(min(W, H) * (0.42 if H > W * 1.35 else 0.50))
        fh = int(fw * 1.20)
        x = max(0, (W - fw) // 2)
        # For tall full-body shots, head is usually in the top ~22% of the frame
        y = max(0, int(H * (0.04 if H > W * 1.35 else 0.06)))
        if y + fh > H:
            y = max(0, H - fh)
        return x, y, fw, fh

    def _sp_detect_face_opencv(self, im):
        """Return (x,y,w,h) via Haar cascades, or None."""
        try:
            import cv2
            import numpy as np
            import os
        except Exception:
            return None
        try:
            W, H = im.size
            # Work on a moderate-size copy for speed / stability
            scale = 1.0
            work = im
            max_side = 720
            if max(W, H) > max_side:
                scale = max_side / float(max(W, H))
                nw, nh = max(32, int(W * scale)), max(32, int(H * scale))
                work = im.resize((nw, nh), resample=1)
            arr = np.array(work.convert('RGB'))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            gray = cv2.equalizeHist(gray)
            base = getattr(cv2.data, 'haarcascades', '') or ''
            names = (
                'haarcascade_frontalface_default.xml',
                'haarcascade_frontalface_alt2.xml',
                'haarcascade_frontalface_alt.xml',
                'haarcascade_profileface.xml',
            )
            cascades = []
            for name in names:
                for cp in (
                    os.path.join(base, name) if base else '',
                    '/usr/share/opencv4/haarcascades/' + name,
                    '/usr/share/opencv/haarcascades/' + name,
                ):
                    if cp and os.path.exists(cp):
                        c = cv2.CascadeClassifier(cp)
                        if not c.empty():
                            cascades.append(c)
                            break
            if not cascades:
                return None

            w0, h0 = work.size
            min_sz = (max(28, w0 // 14), max(28, h0 // 14))
            candidates = []
            # One cascade + one scale pass — enough for posters, much faster on load
            faces = cascades[0].detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=min_sz,
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            for (x, y, fw, fh) in faces:
                candidates.append((int(x), int(y), int(fw), int(fh)))

            if not candidates:
                return None

            best = None
            best_score = -1
            for (x, y, fw, fh) in candidates:
                area = fw * fh
                if area < (w0 * h0) * 0.01:
                    continue
                cy = y + fh / 2.0
                if cy > h0 * 0.82:
                    continue
                # Prefer larger faces higher in frame (headshots / standing portraits)
                height_bias = 1.45 if cy < h0 * 0.40 else (1.15 if cy < h0 * 0.55 else 0.85)
                aspect = fw / float(max(1, fh))
                aspect_bias = 1.2 if 0.65 <= aspect <= 1.15 else 0.75
                score = area * height_bias * aspect_bias
                if score > best_score:
                    best_score = score
                    best = (x, y, fw, fh)
            if not best:
                return None
            # Map back to original coordinates
            if scale != 1.0:
                inv = 1.0 / scale
                x, y, fw, fh = best
                best = (
                    int(round(x * inv)),
                    int(round(y * inv)),
                    max(24, int(round(fw * inv))),
                    max(24, int(round(fh * inv))),
                )
            return best
        except Exception:
            return None

    def _sp_detect_face_skin(self, im):
        """
        Find the dominant face-like skin blob using YCbCr thresholds.
        Returns (x,y,w,h) or None.
        """
        W, H = im.size
        if W < 16 or H < 16:
            return None
        # Search upper 70% — faces rarely sit in the bottom band of portraits
        search_h = max(16, int(H * 0.72))
        # Downsample for speed
        tw = min(160, W)
        th = max(24, int(search_h * (tw / float(W))))
        small = im.convert('RGB').resize((tw, th), resample=1)
        pix = small.load()

        # Binary skin mask
        mask = [[0] * tw for _ in range(th)]
        skin_n = 0
        for y in range(th):
            # Prefer upper rows
            for x in range(tw):
                r, g, b = pix[x, y]
                # YCbCr (integer approx)
                yv = int(0.299 * r + 0.587 * g + 0.114 * b)
                cb = int(128 - 0.168736 * r - 0.331264 * g + 0.5 * b)
                cr = int(128 + 0.5 * r - 0.418688 * g - 0.081312 * b)
                # Broad skin ellipse covering fair → deep brown
                skin = (
                    80 <= yv <= 255
                    and 77 <= cb <= 135
                    and 133 <= cr <= 180
                    and r > 40 and g > 20 and b > 10
                    and abs(r - g) > 5
                )
                # Extra pass for deeper tones (lower Y, still Cb/Cr skin-ish)
                if (not skin) and 35 <= yv <= 140 and 80 <= cb <= 130 and 130 <= cr <= 175 and r >= g >= b:
                    skin = True
                if not skin:
                    continue
                mask[y][x] = 1
                skin_n += 1

        if skin_n < max(30, tw * th * 0.012):
            return None

        # Connected components (4-connected) — keep the best face-like blob
        seen = [[0] * tw for _ in range(th)]
        best = None
        best_score = -1
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        for y0 in range(th):
            for x0 in range(tw):
                if not mask[y0][x0] or seen[y0][x0]:
                    continue
                # BFS
                stack = [(x0, y0)]
                seen[y0][x0] = 1
                minx = maxx = x0
                miny = maxy = y0
                area = 0
                sx = sy = 0
                while stack:
                    x, y = stack.pop()
                    area += 1
                    sx += x
                    sy += y
                    if x < minx: minx = x
                    if x > maxx: maxx = x
                    if y < miny: miny = y
                    if y > maxy: maxy = y
                    for dx, dy in dirs:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < tw and 0 <= ny < th and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = 1
                            stack.append((nx, ny))
                if area < max(40, tw * th * 0.015):
                    continue
                bw = maxx - minx + 1
                bh = maxy - miny + 1
                if bw < 6 or bh < 6:
                    continue
                cx = sx / float(area)
                cy = sy / float(area)
                # Reject huge torso / jersey blobs (common false positive)
                if area > tw * th * 0.28:
                    continue
                if bh > th * 0.55 and cy > th * 0.40:
                    continue
                aspect = bw / float(bh)
                # Faces are roughly square / slightly tall; reject wide jersey bands
                if aspect < 0.45 or aspect > 1.55:
                    continue
                # Strongly prefer blobs in the upper half (heads, not mid-torso)
                if cy > th * 0.62:
                    continue
                center_bias = 1.0 - min(1.0, abs(cx / float(tw) - 0.5) * 1.6)
                height_bias = 1.55 if cy < th * 0.35 else (1.2 if cy < th * 0.50 else 0.65)
                fill = area / float(max(1, bw * bh))
                if fill < 0.28:
                    continue
                # Prefer compact face-sized blobs over large patches
                size_penalty = 1.0
                face_frac = area / float(tw * th)
                if face_frac > 0.16:
                    size_penalty = 0.7
                score = area * (0.55 + 0.45 * center_bias) * height_bias * (0.7 + 0.3 * fill) * size_penalty
                if score > best_score:
                    best_score = score
                    # Expand box slightly to include hair / chin, map to full image
                    pad_x = int(bw * 0.18)
                    pad_y_top = int(bh * 0.35)  # more hair room
                    pad_y_bot = int(bh * 0.18)
                    minx2 = max(0, minx - pad_x)
                    miny2 = max(0, miny - pad_y_top)
                    maxx2 = min(tw - 1, maxx + pad_x)
                    maxy2 = min(th - 1, maxy + pad_y_bot)
                    sx_scale = W / float(tw)
                    sy_scale = search_h / float(th)
                    x = int(minx2 * sx_scale)
                    y = int(miny2 * sy_scale)
                    fw = max(24, int((maxx2 - minx2 + 1) * sx_scale))
                    fh = max(24, int((maxy2 - miny2 + 1) * sy_scale))
                    x = max(0, min(x, W - fw))
                    y = max(0, min(y, H - fh))
                    best = (x, y, fw, fh)
        return best

    def _sp_estimate_face_center(self, im, with_confidence=False):
        """
        Rough face/head anchor via skin mass in the upper frame.
        Returns (cx, cy) or (cx, cy, confidence).
        """
        w, h = im.size
        if w < 8 or h < 8:
            return (0.5, 0.22, 0.0) if with_confidence else (0.5, 0.22)
        search_h = max(8, int(h * 0.65))
        region = im.convert('RGB').crop((0, 0, w, search_h))
        sw = max(56, min(200, w // 2))
        sh = max(56, min(200, search_h // 2))
        small = region.resize((sw, sh), resample=1)
        pixels = small.load()
        xs = ys = n = 0.0
        for y in range(sh):
            row_w = 2.0 if y < sh * 0.45 else (1.1 if y < sh * 0.72 else 0.25)
            for x in range(sw):
                r, g, b = pixels[x, y]
                yv = int(0.299 * r + 0.587 * g + 0.114 * b)
                cb = int(128 - 0.168736 * r - 0.331264 * g + 0.5 * b)
                cr = int(128 + 0.5 * r - 0.418688 * g - 0.081312 * b)
                skin = (77 <= cb <= 135 and 133 <= cr <= 180 and r > 35)
                if (not skin) and 35 <= yv <= 150 and 80 <= cb <= 130 and 130 <= cr <= 175 and r >= g:
                    skin = True
                if not skin:
                    continue
                col_w = 1.4 - abs((x / float(sw)) - 0.5)
                wgt = row_w * max(0.2, col_w)
                xs += x * wgt
                ys += y * wgt
                n += wgt
        conf = n / float(max(1, sw * sh))
        if n < max(8, sw * sh * 0.005):
            out = (0.5, 0.18, conf)
            return out if with_confidence else out[:2]
        cx = (xs / n) / float(sw)
        cy = ((ys / n) / float(sh)) * (search_h / float(h))
        cx = max(0.18, min(0.82, cx))
        cy = max(0.06, min(0.50, cy))
        out = (cx, cy, conf)
        return out if with_confidence else out[:2]

    def _sp_face_crop_box(self, im):
        """Return (left, top, side) square crop box for a PIL image (face-centered)."""
        W, H = im.size
        if W < 4 or H < 4:
            side = max(1, min(W, H))
            return 0, 0, side

        src = im.convert('RGB')
        fx, fy, fw, fh = self._sp_detect_face_box(src)
        fw = max(16, int(fw))
        fh = max(16, int(fh))

        face_cx = fx + fw / 2.0
        eyes_y = fy + fh * 0.38
        hair_y = max(0.0, fy - fh * 0.40)
        face_span = max(fw, fh * 0.95, 1)

        side = int(round(face_span / 0.40))
        side = max(96, side)

        def _cap(v):
            try:
                return max(48, int(v))
            except Exception:
                return 48

        caps = [min(W, H), side]
        if eyes_y > 8:
            caps.append(_cap(eyes_y / 0.34))
        if (H - eyes_y) > 8:
            caps.append(_cap((H - eyes_y) / 0.66))
        if face_cx > 8:
            caps.append(_cap(face_cx / 0.50))
        if (W - face_cx) > 8:
            caps.append(_cap((W - face_cx) / 0.50))
        side = max(48, min(caps))

        left = int(round(face_cx - side * 0.50))
        top = int(round(eyes_y - side * 0.34))
        if hair_y < top:
            top = int(hair_y)
        left = max(0, min(left, W - side))
        top = max(0, min(top, H - side))
        return left, top, side

    def _sp_face_fill_crop(self, im, out_w=640, out_h=640):
        """
        Full-bleed square crop for player cards (fills the placeholder 100%).

        Face-centered with hairroom when the source allows it. The crop window
        always stays inside the image — no letterboxing, no mirroring.
        """
        from PIL import Image
        W, H = im.size
        if W < 4 or H < 4:
            return im.resize((out_w, out_h), Image.LANCZOS)

        src = im.convert('RGB')
        left, top, side = self._sp_face_crop_box(src)
        cropped = src.crop((left, top, left + side, top + side))
        return cropped.resize((out_w, out_h), Image.LANCZOS)

    def _sp_photo_binary(self, player):
        """Load full player photo bytes (never bin_size placeholders)."""
        if not player:
            return False
        raw = player.with_context(bin_size=False).photo
        if not raw:
            return False
        # Guard: bin_size context sometimes leaks as "12.3 Kb" strings
        if isinstance(raw, str) and (
            raw.strip().endswith('Kb') or raw.strip().endswith('Mb')
            or raw.strip().endswith('bytes') or raw.strip().endswith('Gb')
        ):
            return False
        if isinstance(raw, bytes) and len(raw) < 32:
            return False
        return raw

    def _sp_photo_uri(self, binary, size=(420, 420)):
        """
        Player photo → face-centered square data URI for uniform placeholders.
        """
        pack = self._sp_photo_pack(binary, size=size)
        return pack.get('crop_uri') or ''

    def _sp_photo_full_uri(self, binary, max_side=720):
        """Full player photo from DB (no face-crop) for manual pan/zoom editing."""
        pack = self._sp_photo_pack(binary, max_side=max_side)
        return pack.get('full_uri') or ''

    def _sp_photo_pack(self, binary, size=(420, 420), max_side=720,
                       crop_override=None, include_full=True):
        """
        Build cropped card URI + optional full photo URI + crop rect.

        Crop rect (l,t,sw,sh) is normalized to the full image dimensions so the
        editor can open already framed like the poster card.
        Optional crop_override uses a previously saved manual frame (skips face
        detect — big speed win on repeat loads).

        include_full=False for page HTML (full photos are lazy-fetched).
        """
        empty = {'crop_uri': '', 'full_uri': '', 'crop': None}
        if not binary:
            return empty
        from io import BytesIO
        from PIL import Image
        try:
            im = self._sp_open_image(binary)
            if im is None:
                raise ValueError('unreadable image')
            try:
                from PIL import ImageOps
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            im = im.copy()
            if im.mode != 'RGB':
                im = im.convert('RGB')

            w, h = im.size
            side_max = max(w, h)
            if side_max > max_side and side_max > 0:
                scale = float(max_side) / float(side_max)
                im = im.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    Image.BILINEAR,
                )
                w, h = im.size

            used_override = False
            left = top = side = None
            auto_crop = None

            if crop_override and isinstance(crop_override, dict):
                try:
                    cl = float(crop_override.get('l', 0))
                    ct = float(crop_override.get('t', 0))
                    csw = float(crop_override.get('sw', 1))
                    csh = float(crop_override.get('sh', 1))
                    csw = max(0.05, min(1.0, csw))
                    csh = max(0.05, min(1.0, csh))
                    cl = max(0.0, min(1.0 - csw, cl))
                    ct = max(0.0, min(1.0 - csh, ct))
                    ol = int(round(cl * w))
                    ot = int(round(ct * h))
                    oright = int(round((cl + csw) * w))
                    obottom = int(round((ct + csh) * h))
                    ol = max(0, min(w - 1, ol))
                    ot = max(0, min(h - 1, ot))
                    oright = max(ol + 1, min(w, oright))
                    obottom = max(ot + 1, min(h, obottom))
                    oside = min(oright - ol, obottom - ot)
                    if oside < 1:
                        raise ValueError('empty crop')
                    left, top, side = ol, ot, oside
                    crop = {
                        'l': float(left) / float(w),
                        't': float(top) / float(h),
                        'sw': float(side) / float(w),
                        'sh': float(side) / float(h),
                    }
                    # Cheap geometric auto for Reset (skip OpenCV on saved crops)
                    fw = int(min(w, h) * (0.42 if h > w * 1.35 else 0.50))
                    ax = max(0, (w - fw) // 2)
                    ay = max(0, int(h * (0.04 if h > w * 1.35 else 0.06)))
                    if ay + fw > h:
                        ay = max(0, h - fw)
                    auto_crop = {
                        'l': float(ax) / float(w),
                        't': float(ay) / float(h),
                        'sw': float(fw) / float(w),
                        'sh': float(fw) / float(h),
                    }
                    used_override = True
                except Exception:
                    used_override = False
                    left = top = side = None

            if left is None:
                left, top, side = self._sp_face_crop_box(im)
                auto_crop = {
                    'l': float(left) / float(w),
                    't': float(top) / float(h),
                    'sw': float(side) / float(w),
                    'sh': float(side) / float(h),
                }
                crop = dict(auto_crop)

            cropped = im.crop((left, top, left + side, top + side)).resize(
                (size[0], size[1]), Image.BILINEAR
            )

            buf_c = BytesIO()
            cropped.save(buf_c, format='JPEG', quality=80, optimize=True)
            crop_uri = 'data:image/jpeg;base64,%s' % base64.b64encode(
                buf_c.getvalue()
            ).decode('ascii')

            full_uri = ''
            if include_full:
                buf_f = BytesIO()
                im.save(buf_f, format='JPEG', quality=78, optimize=True)
                full_uri = 'data:image/jpeg;base64,%s' % base64.b64encode(
                    buf_f.getvalue()
                ).decode('ascii')

            return {
                'crop_uri': crop_uri,
                'full_uri': full_uri,
                'crop': crop,
                'auto_crop': auto_crop,
                'manual': used_override,
            }
        except Exception:
            _logger.exception('Squad poster photo pack failed; falling back')
            try:
                processed = image_process(binary, size=size, quality=80)
                raw = processed or binary
            except Exception:
                raw = binary
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode('ascii')
                except Exception:
                    raw = base64.b64encode(raw).decode('ascii')
            uri = 'data:image/jpeg;base64,%s' % raw
            return {
                'crop_uri': uri,
                'full_uri': uri,
                'crop': {'l': 0.0, 't': 0.0, 'sw': 1.0, 'sh': 1.0},
                'auto_crop': {'l': 0.0, 't': 0.0, 'sw': 1.0, 'sh': 1.0},
                'manual': False,
            }

    def _sp_initials(self, name):
        parts = [w for w in (name or 'P').split() if w]
        return ''.join(p[0] for p in parts[:2]).upper() or '?'

    def _sp_name_lines(self, name, max_lines=3):
        """Split a brand name into stacked sports-poster lines."""
        parts = [w for w in (name or '').strip().split() if w]
        if not parts:
            return ['']
        if len(parts) == 1:
            return parts[:1]
        if len(parts) == 2 or max_lines <= 2:
            mid = max(1, len(parts) // 2)
            return [' '.join(parts[:mid]), ' '.join(parts[mid:])]
        if len(parts) >= 3 and max_lines >= 3:
            # Prefer one word per line when 3 words; otherwise pack leading words
            if len(parts) == 3:
                return parts[:3]
            if len(parts) == 4:
                return [' '.join(parts[:2]), parts[2], parts[3]]
            mid = max(1, len(parts) - 2)
            return [' '.join(parts[:mid]), parts[-2], parts[-1]]
        mid = max(1, len(parts) // 2)
        return [' '.join(parts[:mid]), ' '.join(parts[mid:])]

    def _sp_team_type_scale(self, name, lines=None):
        """
        Font sizes for team wordmark so long names stay clear of the center logo.
        Returns CSS pixel sizes: line1 (abbr / first), body, only (single-line).
        """
        text = (name or '').strip()
        lines = list(lines or self._sp_name_lines(text, max_lines=3))
        longest = max((len(l) for l in lines), default=len(text))
        chars = len(text.replace(' ', ''))
        nlines = max(1, len([l for l in lines if l]))
        # Shrink more when few long lines (overlap / clip risk)
        if longest >= 14 or chars >= 24:
            return {'line1': 28, 'body': 26, 'only': 28}
        if longest >= 11 or chars >= 18:
            return {'line1': 34, 'body': 30, 'only': 32}
        if longest >= 9 or chars >= 14 or nlines >= 3:
            return {'line1': 40, 'body': 34, 'only': 38}
        if longest >= 7 or chars >= 11:
            return {'line1': 46, 'body': 40, 'only': 44}
        return {'line1': 52, 'body': 44, 'only': 48}

    def _sp_tourn_title_parts(self, name, season_label=''):
        """
        Title stack: LINE1 (gold) / HERO (gold flame) / LINE3 (silver).
        Example: PHYSICAL / MONSOON / PREMIER LEAGUE.

        Uses tournament name only. Season/description only fills gaps when the
        name is a short venue brand — never duplicates words already in the name.
        """
        hero_words = {
            'monsoon', 'champions', 'champion', 'super', 'masters', 'elite',
            'royal', 'thunder', 'blaze', 'inferno', 'empire', 'premier',
            'world', 'national', 'cup', 'trophy', 'slam', 'classic', 'legends',
            'pro', 'prime', 'grand', 'united',
        }
        # Prefer these as the big flame hero when present
        hero_priority = (
            'monsoon', 'champions', 'champion', 'super', 'inferno', 'blaze',
            'thunder', 'premier', 'cup', 'trophy',
        )

        def _tokens(text):
            out = []
            for w in (text or '').strip().split():
                if not w:
                    continue
                if w.upper() == 'SEASON':
                    break
                # skip trailing year-only tokens from title body
                if re.fullmatch(r'20\d{2}', w):
                    continue
                out.append(w)
            return out

        name_parts = _tokens(name)
        season_parts = _tokens(season_label)

        use_parts = list(name_parts)
        name_has_hero = any(w.lower() in hero_words for w in name_parts)
        season_has_hero = any(w.lower() in hero_words for w in season_parts)
        # Borrow league phrase from season when the tournament name has no hero word
        # (venue-style names like "ESTADIO MUD TURF") — never merge both (avoids duplicates).
        if season_parts and season_has_hero and not name_has_hero and len(season_parts) >= 2:
            use_parts = list(season_parts)

        # Deduplicate consecutive / repeated tokens (case-insensitive)
        deduped = []
        seen_l = set()
        for w in use_parts:
            key = w.lower()
            if key in seen_l:
                continue
            seen_l.add(key)
            deduped.append(w)
        parts = deduped

        if not parts:
            return {'line1': '', 'hero': 'TOURNAMENT', 'line3': ''}
        if len(parts) == 1:
            return {'line1': '', 'hero': parts[0].upper(), 'line3': ''}

        hero_i = None
        for pref in hero_priority:
            for i, w in enumerate(parts):
                if w.lower() == pref:
                    hero_i = i
                    break
            if hero_i is not None:
                break
        if hero_i is None:
            for i, w in enumerate(parts):
                if w.lower() in hero_words:
                    hero_i = i
                    break
        if hero_i is None:
            # PHYSICAL MONSOON style: first word line1, second hero, rest line3
            hero_i = 1 if len(parts) >= 2 else 0

        line1 = ' '.join(parts[:hero_i]).strip().upper()
        hero = parts[hero_i].upper()
        line3 = ' '.join(parts[hero_i + 1:]).strip().upper()
        return {'line1': line1, 'hero': hero, 'line3': line3}

    def _sp_hashtag(self, team_name):
        raw = re.sub(r'[^A-Za-z0-9]', '', team_name or '')
        return ('#' + raw.upper()) if raw else ''

    def _sp_role_label(self, player, sport):
        if sport == 'football':
            if player.dominant_position_id and player.dominant_position_id.name:
                return player.dominant_position_id.name
        return (player.role or '').strip()

    def _sp_is_wk(self, role):
        lo = (role or '').lower()
        return any(k in lo for k in ('wicket', 'keeper', 'wk'))

    def _sp_category(self, role, sport):
        lo = (role or '').lower()
        if sport == 'football':
            if any(k in lo for k in ('goal', 'gk', 'keeper')):
                return 'Goalkeepers'
            if any(k in lo for k in ('back', 'defend', 'centre-back', 'center-back', 'cb', 'lb', 'rb')):
                return 'Defenders'
            if any(k in lo for k in ('mid', 'dm', 'cm', 'am', 'wing')):
                return 'Midfielders'
            if any(k in lo for k in ('striker', 'forward', 'attack', 'st', 'cf')):
                return 'Forwards'
            return 'Squad'
        if self._sp_is_wk(lo):
            return 'Wicket Keepers'
        if any(k in lo for k in ('all round', 'all-round', 'allround')):
            return 'All-Rounders'
        if any(k in lo for k in ('bowl', 'spin', 'pace', 'fast', 'medium')):
            return 'Bowlers'
        if any(k in lo for k in ('bat', 'open', 'middle', 'finish')):
            return 'Batters'
        return 'Squad'

    def _sp_strike_force(self, players, sport='cricket'):
        """Role tallies for the Strike Force band under the squad grid."""
        n = len(players or [])
        cats = {}
        for pl in (players or []):
            cat = pl.get('category') or 'Squad'
            cats[cat] = cats.get(cat, 0) + 1

        def _fmt(v):
            try:
                return '%02d' % int(v)
            except Exception:
                return '00'

        if sport == 'football':
            items = [
                {'key': 'players', 'value': _fmt(n), 'label': 'PLAYERS', 'icon': 'players'},
                {'key': 'mid', 'value': _fmt(cats.get('Midfielders', 0)), 'label': 'MIDFIELDERS', 'icon': 'allround'},
                {'key': 'def', 'value': _fmt(cats.get('Defenders', 0) + cats.get('Goalkeepers', 0)), 'label': 'DEFENDERS', 'icon': 'batter'},
                {'key': 'fwd', 'value': _fmt(cats.get('Forwards', 0)), 'label': 'FORWARDS', 'icon': 'bowler'},
            ]
        else:
            ar = cats.get('All-Rounders', 0)
            bat = cats.get('Batters', 0) + cats.get('Wicket Keepers', 0)
            bowl = cats.get('Bowlers', 0)
            # Fold unclassified into batters so totals stay sensible
            other = cats.get('Squad', 0)
            bat += other
            items = [
                {'key': 'players', 'value': _fmt(n), 'label': 'PLAYERS', 'icon': 'players'},
                {'key': 'ar', 'value': _fmt(ar), 'label': 'ALL-ROUNDERS', 'icon': 'allround'},
                {'key': 'bat', 'value': _fmt(bat), 'label': 'BATTERS', 'icon': 'batter'},
                {'key': 'bowl', 'value': _fmt(bowl), 'label': 'BOWLER' if bowl == 1 else 'BOWLERS', 'icon': 'bowler'},
            ]
        return {
            'title': 'THE STRIKE FORCE',
            'tagline': 'ONE TEAM • ONE MISSION • ONE TROPHY',
            'items': items,
        }

    def _sp_grid_cols(self, n):
        """Always 5 square face placeholders per row (max 15 in 3 rows)."""
        return 5

    def _sp_row_gap(self, n_rows):
        """Tight spacing between packed player rows."""
        return 4

    def _sp_player_rows(self, players, cols):
        """Split players into rows so incomplete last rows can be centered."""
        cols = max(1, int(cols or 1))
        rows = []
        plist = list(players or [])
        for i in range(0, len(plist), cols):
            rows.append(plist[i:i + cols])
        return rows

    def _sp_side_cols(self, n):
        return 3

    def _sp_bottom_cols(self, n):
        return 4

    def _sp_fmt_num(self, n):
        try:
            return '{:,}'.format(int(n or 0))
        except Exception:
            return str(n or 0)

    def _sp_build_context(self, auction, group=False):
        team = auction.team_id
        tournament = auction.tournament_id
        sport = (tournament.tournament_type or 'cricket') if tournament else 'cricket'
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

        icon_ids = set(team.key_player_ids.ids) if team else set()
        players_out = []
        ages = []
        bid_vals = []

        # Preserve existing order: key/icon players first, then auction lines
        seen = set()
        ordered = []
        if team:
            for p in team.key_player_ids:
                if p.id not in seen:
                    ordered.append(('icon', p, 0))
                    seen.add(p.id)
        for line in auction.player_ids:
            p = line.player_id
            if not p or p.id in seen:
                if p and p.id in seen:
                    for i, item in enumerate(ordered):
                        if item[1].id == p.id and not item[2]:
                            ordered[i] = (item[0], item[1], int(line.points or 0))
                continue
            ordered.append(('sold', p, int(line.points or 0)))
            seen.add(p.id)

        for kind, p, pts in ordered:
            role = self._sp_role_label(p, sport)
            is_icon = bool(p.icon_player) or (p.id in icon_ids) or kind == 'icon'
            photo_bin = self._sp_photo_binary(p)
            crop_override = None
            raw_crop = (getattr(p, 'squad_poster_crop', None) or '').strip()
            if raw_crop:
                try:
                    parsed = json.loads(raw_crop)
                    if isinstance(parsed, dict) and 'l' in parsed and 'sw' in parsed:
                        crop_override = parsed
                except Exception:
                    crop_override = None
            # Card crops only on page load — full photos lazy-loaded in editor
            pack = self._sp_photo_pack(
                photo_bin, crop_override=crop_override, include_full=False
            ) if photo_bin else {
                'crop_uri': '', 'full_uri': '', 'crop': None,
                'auto_crop': None, 'manual': False,
            }
            photo = pack.get('crop_uri') or ''
            photo_crop = pack.get('crop')
            photo_crop_auto = pack.get('auto_crop') or photo_crop
            photo_manual = bool(pack.get('manual'))
            jersey_raw = (p.jersy_number or '').strip()
            jersey = ''
            if jersey_raw:
                try:
                    jersey = '%02d' % int(jersey_raw)
                except Exception:
                    jersey = jersey_raw[:4]
            # Do not fall back to sl_no — poster no longer shows numbers on cards
            tier_name = ''
            tier_color = ''
            if p.tier_id:
                tier_name = (p.tier_id.name or '').strip()
                tier_color = (p.tier_id.color or '') or ''
            if pts:
                bid_vals.append(pts)
            if getattr(p, 'age', None):
                try:
                    ages.append(int(p.age))
                except Exception:
                    pass
            icon_label = (getattr(p, 'squad_poster_icon_label', None) or '').strip()
            if not icon_label:
                icon_label = 'ICON PLAYER'
            players_out.append({
                'id': p.id,
                'name': (p.name or '').upper(),
                'role': (role or '').upper(),
                'tier': tier_name,
                'tier_color': tier_color,
                'photo_uri': photo,
                'photo_full_uri': '',
                'photo_crop': photo_crop,
                'photo_crop_auto': photo_crop_auto,
                'photo_manual': photo_manual,
                'initials': self._sp_initials(p.name),
                'jersey': jersey,
                'squad_no': jersey,
                'is_icon': is_icon,
                'icon_badge': icon_label,
                'is_wk': self._sp_is_wk(role),
                'points': int(pts or 0),
                'category': self._sp_category(role, sport),
            })

        # Sort: icons first, then points DESC
        players_out.sort(key=lambda pl: (
            0 if pl.get('is_icon') else 1,
            -int(pl.get('points') or 0),
            (pl.get('name') or '').lower(),
        ))

        # Icon / Key players — up to 4 in a featured top row.
        # Remaining squad — up to 15 in a 5×3 grid below.
        icon_players = []
        seen_icon = set()
        if team and team.key_player_ids:
            by_id = {pl.get('id'): pl for pl in players_out}
            for kp in team.key_player_ids:
                pl = by_id.get(kp.id)
                if pl and kp.id not in seen_icon:
                    icon_players.append(pl)
                    seen_icon.add(kp.id)
        for pl in players_out:
            pid = pl.get('id')
            if pl.get('is_icon') and pid not in seen_icon:
                icon_players.append(pl)
                seen_icon.add(pid)
        icon_players = icon_players[:4]
        for pl in icon_players:
            pl['is_icon'] = True

        icon_id_set = {pl.get('id') for pl in icon_players}
        rest_players = [
            pl for pl in players_out
            if pl.get('id') not in icon_id_set
        ][:15]
        for pl in rest_players:
            pl['is_icon'] = False

        has_icon = bool(icon_players)
        icon_hero = icon_players[0] if icon_players else None
        # Full poster roster for stats / strike force
        players_out = icon_players + rest_players

        side_players = []
        bottom_players = []
        grid_players = list(rest_players)
        sym_players = list(rest_players)

        groups = []
        if group and players_out:
            order = (
                ['Goalkeepers', 'Defenders', 'Midfielders', 'Forwards', 'Squad']
                if sport == 'football'
                else ['Batters', 'All-Rounders', 'Bowlers', 'Wicket Keepers', 'Squad']
            )
            cat_alias = {
                'All Rounders': 'All-Rounders',
                'All Rounder': 'All-Rounders',
            }
            bucket = {}
            for pl in players_out:
                cat = cat_alias.get(pl['category'], pl['category'])
                pl['category'] = cat
                bucket.setdefault(cat, []).append(pl)
            for label in order:
                if bucket.get(label):
                    groups.append({'label': label.upper(), 'players': bucket[label]})
            for label, pls in bucket.items():
                if label not in order:
                    groups.append({'label': (label or 'Squad').upper(), 'players': pls})

        total_purse = int(auction.total_point or 0)
        remaining = int(auction.remaining_points or 0)
        spent = max(total_purse - remaining, 0)
        n_players = len(players_out)
        n_grid = len(rest_players)
        grid_cols = self._sp_grid_cols(n_grid or n_players)
        side_cols = 3
        bottom_cols = 5
        grid_rows = max(1, (n_grid + grid_cols - 1) // grid_cols) if n_grid else (0 if has_icon else 1)
        row_gap = self._sp_row_gap(grid_rows)
        sparse_squad = False
        has_bottom = False
        player_rows = self._sp_player_rows(rest_players, grid_cols)
        strike_force = self._sp_strike_force(players_out, sport=sport)

        stats = {
            'players': n_players,
            'budget': self._sp_fmt_num(total_purse),
            'spent': self._sp_fmt_num(spent),
            'remaining': self._sp_fmt_num(remaining),
            'owner': (team.manager or '') if team else '',
            'highest': self._sp_fmt_num(max(bid_vals)) if bid_vals else '',
            'lowest': self._sp_fmt_num(min(bid_vals)) if bid_vals else '',
            'avg_age': '',
        }
        if ages:
            stats['avg_age'] = str(int(round(sum(ages) / float(len(ages)))))

        venue = ''
        date_label = ''
        season_label = ''
        season_raw = ''
        team_count = 0
        sponsors = []
        tourn_logo = ''
        bg_uri = ''
        tournament_name = 'Tournament'
        organizer_name = ''
        if tournament:
            tournament_name = (tournament.name or '').strip() or 'Tournament'
            venue = (tournament.auction_venue or tournament.venue or '').strip()
            if tournament.auction_date:
                try:
                    date_label = tournament.auction_date.strftime('%d %b %Y')
                except Exception:
                    date_label = str(tournament.auction_date)
            else:
                date_label = tournament.format_tournament_dates(fmt='%d %b %Y') or ''
            season_raw = (tournament.description or '').strip()
            season_label = season_raw
            if len(season_label) > 48:
                season_label = season_label[:45] + '…'
            team_count = len(tournament.team_ids)
            tourn_logo = self._sp_logo_uri(tournament.logo, size=(320, 320))
            for adv in (tournament.advertiser_ids or []):
                if not adv.image:
                    continue
                sponsors.append({
                    'name': adv.name or 'Sponsor',
                    'uri': self._sp_logo_uri(adv.image, size=(360, 360)),
                })
                if len(sponsors) >= 10:
                    break
            if tournament.poster_image:
                bg_uri = self._sp_b64_uri(
                    tournament.poster_image, mime='image/jpeg',
                    size=(self.SP_CANVAS_W, self.SP_CANVAS_H), quality=82,
                )
            else:
                bg_uri = ''
            organizer_name = (tournament.organizer_name or '').strip()

        team_name = ((team.name if team else '') or 'Team').strip()
        manager = ((team.manager if team else '') or '').strip()
        team_name_lines = self._sp_name_lines(team_name, max_lines=3)
        team_type = self._sp_team_type_scale(team_name, lines=team_name_lines)
        # Reference copy hierarchy — overridable later via tournament fields if added
        motto = ''
        battle_cry = ''
        footer_slogan = ''
        tagline = ''

        sport_label = (sport or 'cricket').title()
        sport_icon = '🏏' if sport == 'cricket' else ('⚽' if sport == 'football' else '🏅')
        tourn_parts = self._sp_tourn_title_parts(tournament_name, season_label=season_raw or season_label)
        # Season chip under the title — keep "SEASON N" only (avoid repeating league words)
        _sm = re.search(r'(SEASON\s*\d+)', (season_raw or season_label or ''), flags=re.I)
        if _sm:
            season_label = _sm.group(1).upper()
        elif not season_label:
            season_label = 'SEASON'

        return {
            'theme': theme,
            'sport': sport,
            'sport_label': sport_label,
            'sport_icon': sport_icon,
            'tournament_name': tournament_name,
            'tournament_name_lines': self._sp_name_lines(tournament_name, max_lines=3),
            'tourn_line1': tourn_parts.get('line1') or '',
            'tourn_hero': tourn_parts.get('hero') or tournament_name,
            'tourn_line3': tourn_parts.get('line3') or '',
            'season_label': season_label,
            'organizer_name': organizer_name,
            'venue': venue,
            'date_label': date_label,
            'team_count': team_count,
            'tourn_logo_uri': tourn_logo,
            'team_name': team_name,
            'team_name_lines': team_name_lines,
            'team_type_line1': team_type['line1'],
            'team_type_body': team_type['body'],
            'team_type_only': team_type['only'],
            'team_logo_uri': self._sp_logo_uri(team.logo, size=(360, 360)) if team else '',
            'players': players_out,
            'player_rows': player_rows,
            'grid_players': grid_players if has_icon else players_out,
            'side_players': side_players,
            'bottom_players': bottom_players,
            'sym_players': sym_players,
            'icon_player': icon_hero if has_icon else None,
            'icon_players': icon_players if has_icon else [],
            'icon_count': len(icon_players) if has_icon else 0,
            'has_icon': has_icon,
            'has_bottom': has_bottom,
            'sparse_squad': sparse_squad,
            'side_cols': side_cols,
            'bottom_cols': bottom_cols,
            'grouped': bool(group and groups),
            'groups': groups if group else [],
            'grid_cols': grid_cols,
            'grid_rows': grid_rows,
            'row_gap': row_gap,
            'palette': 'ember-orange',
            'dense': '1',
            'stats': stats,
            'manager': manager,
            'manager_initials': self._sp_initials(manager),
            'sponsors': sponsors,
            'has_sponsors': bool(sponsors),
            'strike_force': strike_force,
            'player_count': n_players,
            'bg_uri': bg_uri,
            'tagline': tagline,
            'motto': motto,
            'battle_cry': battle_cry,
            'footer_slogan': footer_slogan,
            'hashtag': self._sp_hashtag(team_name),
            'brand_url': 'www.auctionchamp.live',
            'canvas_w': self.SP_CANVAS_W,
            'canvas_h': self.SP_CANVAS_H,
            'res_company': request.env.company,
            'db_name': request.session.db or '',
        }

    def _sp_bind_db_and_user(self, db_name=None):
        """
        Pin session DB (multi-db safe) and require a logged-in user.
        Returns a redirect Response if the caller should stop, else None.
        """
        if db_name:
            if request.session.db != db_name:
                try:
                    valid_dbs = http.db_list(force=True)
                except Exception:
                    valid_dbs = []
                if valid_dbs and db_name not in valid_dbs:
                    return request.not_found()
                request.session.db = db_name
                return werkzeug.utils.redirect(request.httprequest.url, 302)
        elif not request.session.db:
            # Last resort: single matching DB
            try:
                from odoo.http import db_monodb
                mono = db_monodb(request.httprequest)
            except Exception:
                mono = None
            if mono:
                request.session.db = mono
                return werkzeug.utils.redirect(request.httprequest.url, 302)
            return request.not_found()

        if not request.session.uid:
            target = request.httprequest.path
            qs = request.httprequest.query_string.decode() if request.httprequest.query_string else ''
            if qs:
                target += '?' + qs
            return werkzeug.utils.redirect(
                '/web/login?' + werkzeug.urls.url_encode({'redirect': target}), 302
            )

        # auth='none' leaves uid unset — bind env to the logged-in user
        request.uid = request.session.uid
        request._env = None
        return None

    def _sp_render_poster_page(self, auction_id, **kw):
        """Build the squad poster HTML response (shared by db / non-db routes)."""
        auction = request.env['auction.auction'].sudo().browse(auction_id)
        if not auction.exists():
            return request.not_found()
        group = str(kw.get('group') or '').lower() in ('1', 'true', 'yes')
        ctx = self._sp_build_context(auction, group=group)
        projector_mode = str(
            kw.get('projector') or request.params.get('projector') or ''
        ).lower() in ('1', 'true', 'yes')
        ctx['projector_mode'] = projector_mode
        html = request.render('auction_module.squad_poster_template', ctx, lazy=False)
        if isinstance(html, bytes):
            body = html
        else:
            body = str(html or '').encode('utf-8')
        if projector_mode:
            # Clean projector iframe — no crop editor / photo maps
            return request.make_response(
                body,
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )
        photo_map = {}
        crop_map = {}
        auto_map = {}
        label_map = {}
        for pl in (ctx.get('players') or []):
            pid = pl.get('id')
            if not pid:
                continue
            sid = str(pid)
            # Full photos are lazy-loaded — do not embed megabytes of base64
            if pl.get('photo_crop'):
                crop_map[sid] = pl.get('photo_crop')
            if pl.get('photo_crop_auto'):
                auto_map[sid] = pl.get('photo_crop_auto')
            if pl.get('is_icon') and pl.get('icon_badge'):
                label_map[sid] = pl.get('icon_badge')
        db_name = request.session.db or ''
        map_tag = (
            b'\n<script>window.__spAuctionId='
            + str(int(auction_id)).encode('utf-8')
            + b';window.__spDbName='
            + json.dumps(db_name).encode('utf-8')
            + b';window.__spFullPhotos='
            + json.dumps(photo_map).encode('utf-8')
            + b';window.__spPhotoCrops='
            + json.dumps(crop_map).encode('utf-8')
            + b';window.__spAutoCrops='
            + json.dumps(auto_map).encode('utf-8')
            + b';window.__spIconLabels='
            + json.dumps(label_map).encode('utf-8')
            + b';</script>'
        )
        editor_tag = (
            map_tag
            + b'\n<script src="/auction_module/static/src/js/squad_poster_editor.js?v=279">'
            + b'</script>\n</body>'
        )
        if b'squad_poster_editor.js' not in body:
            if b'</body>' in body:
                body = body.replace(b'</body>', editor_tag, 1)
            elif b'</BODY>' in body:
                body = body.replace(b'</BODY>', editor_tag, 1)
            else:
                body = body + editor_tag
        return request.make_response(
            body,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )

    @http.route(['/auction/squad-poster/<int:auction_id>/full-photo/<int:player_id>',
                 '/<string:db_name>/auction/squad-poster/<int:auction_id>/full-photo/<int:player_id>'],
                type='json', auth='user', website=False)
    def squad_poster_full_photo(self, auction_id, player_id, db_name=None, **kw):
        """Lazy-load full player photo for the squad poster editor."""
        auction = request.env['auction.auction'].sudo().browse(auction_id)
        if not auction.exists():
            return {'ok': False, 'error': 'auction_not_found'}
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return {'ok': False, 'error': 'player_not_found'}
        photo_bin = self._sp_photo_binary(player)
        if not photo_bin:
            return {'ok': False, 'error': 'no_photo'}
        pack = self._sp_photo_pack(photo_bin, include_full=True, max_side=720)
        uri = pack.get('full_uri') or pack.get('crop_uri') or ''
        if not uri:
            return {'ok': False, 'error': 'encode_failed'}
        return {'ok': True, 'uri': uri, 'player_id': int(player_id)}

    @http.route(['/auction/squad-poster/<int:auction_id>/photo-crops',
                 '/<string:db_name>/auction/squad-poster/<int:auction_id>/photo-crops'],
                type='json', auth='user', website=False)
    def squad_poster_save_crops(self, auction_id, crops=None, clear_ids=None,
                                icon_labels=None, db_name=None, **kw):
        """Persist manual pan/zoom crop windows and icon badge labels."""
        auction = request.env['auction.auction'].sudo().browse(auction_id)
        if not auction.exists():
            return {'ok': False, 'error': 'auction_not_found'}
        Player = request.env['auction.team.player'].sudo()
        saved = 0
        cleared = 0
        labels_saved = 0
        for pid, crop in (crops or {}).items():
            try:
                player = Player.browse(int(pid))
            except Exception:
                continue
            if not player.exists():
                continue
            if not isinstance(crop, dict):
                continue
            try:
                payload = {
                    'l': float(crop.get('l', 0)),
                    't': float(crop.get('t', 0)),
                    'sw': float(crop.get('sw', 1)),
                    'sh': float(crop.get('sh', 1)),
                }
            except Exception:
                continue
            player.write({'squad_poster_crop': json.dumps(payload)})
            saved += 1
        for pid in (clear_ids or []):
            try:
                player = Player.browse(int(pid))
            except Exception:
                continue
            if player.exists() and player.squad_poster_crop:
                player.write({'squad_poster_crop': False})
                cleared += 1
        for pid, label in (icon_labels or {}).items():
            try:
                player = Player.browse(int(pid))
            except Exception:
                continue
            if not player.exists():
                continue
            text = (label or '').strip()
            if not text:
                text = False
            elif len(text) > 28:
                text = text[:28]
            player.write({'squad_poster_icon_label': text})
            labels_saved += 1
        return {
            'ok': True,
            'saved': saved,
            'cleared': cleared,
            'labels_saved': labels_saved,
        }

    @http.route([
        '/<string:db_name>/auction/projector/<string:tournament_slug>/squad-poster/<int:auction_id>',
    ], type='http', auth='none', website=False, sitemap=False, csrf=False)
    def auction_projector_squad_poster(self, db_name, tournament_slug, auction_id, **kw):
        """Public projector-safe squad poster (no login). Used by the PPT deck."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return self._not_found()
            # Only after auction is officially complete (same logic as Thank You)
            wait = _pj_wait_phase(tournament)
            if wait.get('phase') != 'completed':
                return request.make_response(
                    '<!DOCTYPE html><html><body style="font-family:system-ui;padding:24px;'
                    'background:#111;color:#eee"><h2>Squad Posters locked</h2>'
                    '<p>Available only after the auction is officially complete.</p>'
                    '</body></html>',
                    headers=[('Content-Type', 'text/html; charset=utf-8')],
                    status=403,
                )
            auction = request.env['auction.auction'].sudo().browse(int(auction_id))
            if not auction.exists() or auction.tournament_id.id != tournament.id:
                return self._not_found()
            return self._sp_render_poster_page(auction.id, projector=1, **kw)

    @http.route(['/auction/squad-poster/<int:auction_id>',
                 '/<string:db_name>/auction/squad-poster/<int:auction_id>'],
                type='http', auth='none', website=False, csrf=False)
    def squad_poster_page(self, auction_id, db_name=None, **kw):
        """Premium 2:3 franchise squad poster (1024×1536) with hi-res PNG/JPG export."""
        redirect = self._sp_bind_db_and_user(db_name=db_name)
        if redirect is not None:
            return redirect
        return self._sp_render_poster_page(auction_id, **kw)

    # ── Player Registration Form ──────────────────────────────────────────────

    @http.route('/player/register', type='http', auth='none', website=False,
                methods=['GET'], csrf=False)
    def player_register_legacy(self, **kw):
        """Redirect legacy /player/register URL to the db-slug-based URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('active', '=', True)], limit=1
            )
            if tournament and tournament.slug:
                return werkzeug.utils.redirect('/{}/{}/player/register'.format(
                    db_name, tournament.slug), 301)
        return self._not_found()

    @http.route('/<string:tournament_slug>/player/register', type='http', auth='none', website=False,
                methods=['GET'], csrf=False)
    def player_register_slug_legacy(self, tournament_slug, **kw):
        """Redirect old /<slug>/player/register to the db-prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        return werkzeug.utils.redirect('/{}/{}/player/register'.format(
            db_name, tournament_slug), 301)

    @http.route('/<string:db_name>/<string:tournament_slug>/player/register', type='http', auth='none', website=False,
                methods=['GET', 'POST'], csrf=False)
    def player_register(self, db_name, tournament_slug, **kw):
        """Public player self-registration form. Creates a draft player record."""
        return self._player_register_core(db_name, tournament_slug, admin=False, **kw)

    @http.route('/<string:db_name>/<string:tournament_slug>/player/register/admin', type='http',
                auth='none', website=False, methods=['GET', 'POST'], csrf=False)
    def player_register_admin(self, db_name, tournament_slug, **kw):
        """Organiser registration: unlock once with tournament code, ignore public open flag.

        Stays available while draft count is below max_registrations. When the
        allotment is full, both public and admin URLs show squad complete.
        """
        return self._player_register_core(db_name, tournament_slug, admin=True, **kw)

    def _player_register_core(self, db_name, tournament_slug, admin=False, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tournament:
                return self._not_found()

            theme = tournament.player_display_template or 'vanilla'
            register_path = self._reg_path(db_name, tournament_slug, admin=admin)
            football_positions, football_styles, football_strengths = self._reg_football_lookups(tournament)
            max_reg, current_count, slots_left, is_full = self._reg_capacity(tournament)

            # Admin path: require tournament-code unlock once per browser
            if admin:
                if request.httprequest.method == 'POST' and request.params.get('admin_unlock'):
                    code = request.params.get('tournament_code') or ''
                    if self._reg_admin_try_unlock(tournament, code):
                        resp = werkzeug.utils.redirect(register_path, 303)
                        return self._reg_admin_grant(tournament, response=resp)
                    return self._render_admin_register_unlock(
                        tournament, db_name, tournament_slug, theme=theme,
                        error='Invalid tournament code. Please try again.',
                        entered_code=code,
                    )
                if not self._reg_admin_unlocked(tournament):
                    return self._render_admin_register_unlock(
                        tournament, db_name, tournament_slug, theme=theme,
                    )

            # Gate:
            #  - public: closed when registration_open is False OR allotment full
            #  - admin:  closed only when allotment full (can register while public is closed)
            public_closed = (not tournament.registration_open) and not admin
            if public_closed or is_full:
                if is_full and tournament.registration_open:
                    try:
                        tournament.sudo().write({'registration_open': False})
                    except Exception:
                        _logger.warning(
                            'player_register: could not auto-close registration for tournament %s',
                            tournament.id, exc_info=True,
                        )
                tiers_all = request.env['auction.player.tier'].sudo().search(
                    [('is_an_icon_tier', '=', False), ('tournament_id', '=', tournament.id)],
                    order='name asc'
                )
                html = request.render('auction_module.player_registration_form', {
                    'tournament': tournament,
                    'tiers': tiers_all,
                    'theme': theme,
                    'db_name': db_name,
                    'tournament_slug': tournament_slug,
                    'registration_closed': True,
                    'slots_left': 0,
                    'max_registrations': max_reg,
                    'current_count': current_count,
                    'positions': football_positions,
                    'styles': football_styles,
                    'strengths': football_strengths,
                    'payment_proof_required': bool(tournament.payment_proof_required),
                    'admin_registration': admin,
                    'register_path': register_path,
                }, lazy=False)
                return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

            tiers = request.env['auction.player.tier'].sudo().search(
                [('is_an_icon_tier', '=', False), ('tournament_id', '=', tournament.id)],
                order='name asc'
            )

            base_ctx = {
                'tournament': tournament,
                'tiers': tiers,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug,
                'slots_left': slots_left,
                'max_registrations': max_reg,
                'current_count': current_count,
                'positions': football_positions,
                'styles': football_styles,
                'strengths': football_strengths,
                'payment_proof_required': bool(tournament.payment_proof_required),
                'admin_registration': admin,
                'register_path': register_path,
            }

            if request.httprequest.method == 'POST':
                # Ignore unlock-only posts that somehow reach here
                if admin and request.params.get('admin_unlock'):
                    return werkzeug.utils.redirect(register_path, 303)
                try:
                    # Re-check capacity under race before create
                    _mr, _cc, _sl, full_now = self._reg_capacity(tournament)
                    if full_now:
                        return werkzeug.utils.redirect(register_path, 303)

                    pay_resp = self._registration_payment_post(
                        db_name, tournament_slug, tournament, dict(base_ctx)
                    )
                    if pay_resp is not None:
                        return pay_resp

                    vals = _build_player_vals_from_post(request, tournament)
                    player = request.env['auction.team.player'].sudo().create(vals)
                    try:
                        self._registration_after_create(player, db_name)
                    except Exception:
                        _logger.exception(
                            'registration after-create hook failed for player %s',
                            player.id,
                        )
                    # Close public registration when allotment hits max
                    _mr2, _cc2, _sl2, full_after = self._reg_capacity(tournament)
                    if full_after and tournament.registration_open:
                        try:
                            tournament.sudo().write({'registration_open': False})
                        except Exception:
                            _logger.warning(
                                'player_register: could not auto-close after create for tournament %s',
                                tournament.id, exc_info=True,
                            )
                    from urllib.parse import urlencode
                    qs = urlencode({'success': '1', 'player_id': player.id})
                    return werkzeug.utils.redirect('%s?%s' % (register_path, qs), 303)
                except Exception as e:
                    ctx = dict(base_ctx, error=str(e))
                    try:
                        html = request.render('auction_module.player_registration_form', ctx, lazy=False)
                    except Exception:
                        _logger.exception(
                            'player_register: template render failed for tournament %s (slug=%s)',
                            tournament.id, tournament_slug,
                        )
                        return request.make_response(
                            b'<h1>Registration page temporarily unavailable. Please try again.</h1>',
                            [('Content-Type', 'text/html; charset=utf-8')],
                        )
                    return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

            success = kw.get('success') == '1'
            try:
                player_id_str = kw.get('player_id', '')
                player_id = int(player_id_str) if player_id_str else None
            except (ValueError, TypeError):
                player_id = None

            ctx = dict(base_ctx, success=success, player_id=player_id)
            ctx = self._registration_payment_get_ctx(ctx, tournament, kw)
            ctx = self._registration_success_ctx(ctx, tournament, kw)

            try:
                html = request.render('auction_module.player_registration_form', ctx, lazy=False)
            except Exception:
                _logger.exception(
                    'player_register: template render failed for tournament %s (slug=%s)',
                    tournament.id, tournament_slug,
                )
                return request.make_response(
                    b'<h1>Registration page temporarily unavailable. Please try again.</h1>',
                    [('Content-Type', 'text/html; charset=utf-8')],
                )
            return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    def _registration_payment_post(self, db_name, tournament_slug, tournament, render_ctx):
        """Hook for payment gateway modules. Return an HTTP response to take over POST, or None."""
        return None

    def _registration_payment_get_ctx(self, ctx, tournament, kw):
        """Hook for payment gateway modules to enrich the registration GET context."""
        return ctx

    def _registration_after_create(self, player, db_name):
        """Hook after a public registration creates a player (notify / WhatsApp / email)."""
        return None

    def _registration_success_ctx(self, ctx, tournament, kw):
        """Hook to enrich registration success page context."""
        return ctx

    @http.route('/<string:db_name>/<string:tournament_slug>/player/check_mobile',
                type='json', auth='none', website=False, csrf=False, methods=['POST'])
    def player_check_mobile(self, db_name, tournament_slug, mobile=None, **kw):
        """Check if a mobile number is already registered for this tournament."""
        with self._with_db(db_name) as ok:
            if not ok or not mobile:
                return {'duplicate': False}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tournament:
                return {'duplicate': False}
            mobile = (mobile or '').strip()
            count = request.env['auction.team.player'].sudo().search_count([
                ('tournament_id', '=', tournament.id),
                ('contact', '=', mobile),
                ('state', '=', 'draft'),
            ])
            return {'duplicate': count > 0, 'count': count}

    @http.route('/player/card/<int:player_id>', type='http', auth='none', website=False, sitemap=False)
    def player_card_download_legacy(self, player_id, **kw):
        """Redirect legacy /player/card/<id> to db-prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
                return self._not_found()
        return werkzeug.utils.redirect('/{}/player/card/{}'.format(db_name, player_id), 301)

    @http.route('/<string:db_name>/player/card_preview/<int:player_id>',
                type='http', auth='none', website=False, sitemap=False)
    def player_card_preview(self, db_name, player_id, **kw):
        """Render the player card as inline HTML for preview (no PDF conversion)."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            player = request.env['auction.team.player'].sudo().browse(player_id)
            if not player.exists():
                return self._not_found()

            tournament = player.tournament_id
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

            if tournament and tournament.tournament_type == 'football':
                report_ref = 'auction_module.action_report_player_card_football'
            else:
                report_map = {
                    'vanilla':      'auction_module.action_report_player_card',
                    'butterscotch': 'auction_module.action_report_player_card_butterscotch',
                    'strawberry':   'auction_module.action_report_player_card_strawberry',
                    'cherry':       'auction_module.action_report_player_card_cherry',
                    'pistah':       'auction_module.action_report_player_card_pistah',
                    'lemon':        'auction_module.action_report_player_card_lemon',
                    'blackberry':   'auction_module.action_report_player_card_blackberry',
                }
                report_ref = report_map.get(theme, 'auction_module.action_report_player_card')

            try:
                report = request.env.ref(report_ref).sudo()
                html_content, _mime = report._render_qweb_html([player_id])
            except Exception:
                _logger.exception("Card preview HTML render failed player_id=%s", player_id)
                return self._not_found()

            # Inject CSS to strip all extra whitespace outside the card border
            cleanup = (
                b'<style>'
                b'html,body{'
                b'  margin:0!important;padding:0!important;'
                b'  overflow:hidden!important;height:auto!important;'
                b'  background:#ffffff!important;'
                b'}'
                b'.page{margin:0!important;padding:0!important;}'
                b'</style>'
            )
            if isinstance(html_content, str):
                html_content = html_content.encode('utf-8')
            html_content = html_content.replace(b'</head>', cleanup + b'</head>', 1)

        return request.make_response(
            html_content,
            headers=[
                ('Content-Type', 'text/html; charset=utf-8'),
                ('Cache-Control', 'no-store'),
                ('X-Frame-Options', 'SAMEORIGIN'),
            ]
        )

    @http.route('/<string:db_name>/player/card/<int:player_id>', type='http', auth='none', website=False, sitemap=False)
    def player_card_download(self, db_name, player_id, **kw):
        """Stream the themed player-card PDF for the given player (public, read-only)."""
        import time
        t0 = time.monotonic()
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            player = request.env['auction.team.player'].sudo().browse(player_id)
            if not player.exists():
                return self._not_found()

            # Ensure print-sized photo/logo so wkhtmltopdf does not embed huge uploads.
            if player.photo and not player.photo_card:
                player._compute_photo_card()
                player.flush(['photo_card'])
            tournament = player.tournament_id
            if tournament and tournament.logo and not tournament.logo_card:
                tournament._compute_logo_card()
                tournament.flush(['logo_card'])

            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

            if tournament and tournament.tournament_type == 'football':
                report_ref = 'auction_module.action_report_player_card_football'
            else:
                report_map = {
                    'vanilla':      'auction_module.action_report_player_card',
                    'butterscotch': 'auction_module.action_report_player_card_butterscotch',
                    'strawberry':   'auction_module.action_report_player_card_strawberry',
                    'cherry':       'auction_module.action_report_player_card_cherry',
                    'pistah':       'auction_module.action_report_player_card_pistah',
                    'lemon':        'auction_module.action_report_player_card_lemon',
                    'blackberry':   'auction_module.action_report_player_card_blackberry',
                }
                report_ref = report_map.get(theme, 'auction_module.action_report_player_card')

            try:
                report = request.env.ref(report_ref).sudo().with_context(
                    skip_player_card_compress=True,
                )
                pdf_content, _mime = report._render_qweb_pdf([player_id])
            except Exception:
                _logger.exception(
                    "Player card PDF generation failed for player_id=%s theme=%s",
                    player_id, theme
                )
                # Return a readable HTML error page instead of a raw 500
                body = u"""
                    <html><head><meta charset="UTF-8"/>
                    <style>
                        body{{font-family:sans-serif;display:flex;align-items:center;
                              justify-content:center;min-height:100vh;margin:0;
                              background:#f8f8f8;}}
                        .box{{text-align:center;padding:2rem;max-width:480px;}}
                        h2{{color:#c0392b;}} p{{color:#555;line-height:1.6;}}
                        a{{color:#2980b9;}}
                    </style></head>
                    <body><div class="box">
                        <h2>&#9888; Player Card Unavailable</h2>
                        <p>We could not generate your player card right now.<br/>
                        This is usually caused by a large or unsupported photo format
                        uploaded from a mobile device.</p>
                        <p>Please try again in a moment, or contact the organiser
                        if the problem persists.</p>
                        <p><a href="javascript:history.back()">&#8592; Go Back</a></p>
                    </div></body></html>
                """.format()
                return request.make_response(
                    body.encode('utf-8'),
                    headers=[
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Cache-Control', 'no-store'),
                    ],
                    status=503,
                )

            filename = 'PlayerCard_%s.pdf' % (player.name or player_id)
            _logger.info(
                'Player card PDF ready player_id=%s size=%.0fKB in %.2fs',
                player_id,
                len(pdf_content) / 1024.0,
                time.monotonic() - t0,
            )
        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ]
        )

    @http.route('/<string:db_name>/player/card_status/<int:player_id>',
                type='http', auth='none', website=False, sitemap=False)
    def player_card_status_jpg(self, db_name, player_id, **kw):
        """Stream a vertical Instagram Status (9:16) player card as JPG.

        Uses the same portrait template as *Download Player Cards (ZIP)*.
        Public so newly registered players can download from the success page.
        """
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            player = request.env['auction.team.player'].sudo().browse(player_id)
            if not player.exists():
                return self._not_found()

            try:
                jpg = player.render_instagram_status_jpg()
            except Exception:
                _logger.exception(
                    'Instagram status JPG failed for player_id=%s', player_id)
                jpg = None

            if not jpg:
                body = (
                    '<html><head><meta charset="UTF-8"/>'
                    '<style>body{font-family:sans-serif;display:flex;align-items:center;'
                    'justify-content:center;min-height:100vh;margin:0;background:#f8f8f8}'
                    '.box{text-align:center;padding:2rem;max-width:480px}'
                    'h2{color:#c0392b}p{color:#555;line-height:1.6}</style></head>'
                    '<body><div class="box">'
                    '<h2>&#9888; Status Card Unavailable</h2>'
                    '<p>We could not generate your Instagram status card right now.<br/>'
                    'Please try again in a moment, or use the PDF player card download.</p>'
                    '<p><a href="javascript:history.back()">&#8592; Go Back</a></p>'
                    '</div></body></html>'
                )
                return request.make_response(
                    body.encode('utf-8'),
                    headers=[
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Cache-Control', 'no-store'),
                    ],
                    status=503,
                )

            safe = re.sub(
                r'[^A-Za-z0-9]+', '_',
                (player.name or ('Player_%s' % player_id)).strip()
            ).strip('_') or 'Player'
            filename = 'Instagram_Status_%s.jpg' % safe

        return request.make_response(
            jpg,
            headers=[
                ('Content-Type', 'image/jpeg'),
                ('Content-Length', len(jpg)),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
                ('Cache-Control', 'private, max-age=60'),
            ],
        )


    # ── Tournament Registration (public) ───────────────────────────────────────

    @http.route('/tournament/register', type='http', auth='none', website=False, sitemap=False,
                methods=['GET', 'POST'], csrf=False)
    def tournament_register(self, **kw):
        """Public organiser tournament registration page."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            dbs = db_list(force=True, httprequest=request.httprequest)
            db_name = dbs[0] if dbs else None
        if not db_name:
            return self._not_found()

        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            # Find a sample player to show for card preview (any player with a photo)
            sample_player = request.env['auction.team.player'].sudo().search(
                [('photo', '!=', False)], limit=1
            )
            sample_player_id = sample_player.id if sample_player else 0
            res_company = request.env['res.company'].sudo().search([], limit=1)

            if request.httprequest.method == 'POST':
                return self._tournament_register_post(db_name, sample_player_id, res_company, **kw)

            # PRG: render success view when redirected back after a successful POST
            success = kw.get('success') == '1'
            return request.render(
                'auction_module.tournament_registration_form',
                {
                    'db_name': db_name,
                    'success': success,
                    'error': None,
                    'tournament_name': kw.get('name', '') if success else '',
                    'tournament_code': kw.get('code', '—') if success else '—',
                    'sample_player_id': sample_player_id,
                    'res_company': res_company,
                }
            )

    def _tournament_register_post(self, db_name, sample_player_id, res_company, **kw):
        """Handle POST from the tournament registration form."""
        import base64

        post = request.httprequest.form
        files = request.httprequest.files

        def _read_file(field_name):
            f = files.get(field_name)
            if f and f.filename:
                return base64.b64encode(f.read())
            return False

        def _str(key, default=''):
            val = post.get(key, default)
            return val.strip() if isinstance(val, str) else default

        try:
            vals = {
                'name': _str('name') or 'New Tournament',
                'description': _str('description') or 'Season 1',
                'tournament_type': _str('tournament_type') or 'cricket',
                'player_display_template': _str('player_display_template') or 'vanilla',
                'venue': _str('venue'),
                'organizer_name': _str('organizer_name'),
                'organizer_contact': _str('organizer_contact'),
                'whatsapp_group_link': _str('whatsapp_group_link'),
                'rules_regulations': _str('rules_regulations'),
                'payment_instruction': _str('payment_instruction'),
                'enable_jersey_section': bool(post.get('enable_jersey_section')),
                # Contact unmask requires privacy agreement in Tournament Master — never enable from public form.
                'expose_player_contact': False,
            }

            # Dates — support multiple days for multi-day tournaments
            from odoo.fields import Date
            date_strs = []
            raw_dates = post.getlist('tournament_date') if hasattr(post, 'getlist') else [post.get('tournament_date')]
            for date_str in raw_dates:
                if isinstance(date_str, str):
                    date_str = date_str.strip()
                if date_str:
                    date_strs.append(date_str)
            # Deduplicate while preserving order
            seen = set()
            unique_dates = []
            for date_str in date_strs:
                if date_str in seen:
                    continue
                seen.add(date_str)
                try:
                    unique_dates.append(Date.to_date(date_str))
                except Exception:
                    pass
            if unique_dates:
                unique_dates = sorted(unique_dates)
                vals['tournament_date'] = unique_dates[0]
                vals['tournament_dates'] = ','.join(
                    Date.to_string(d) for d in unique_dates
                )

            # Numeric
            try:
                vals['max_registrations'] = int(post.get('max_registrations', 0))
            except (ValueError, TypeError):
                vals['max_registrations'] = 0

            # Images
            logo = _read_file('logo')
            if logo:
                vals['logo'] = logo
            poster = _read_file('poster_image')
            if poster:
                vals['poster_image'] = poster
            qr = _read_file('payment_qr_image')
            if qr:
                vals['payment_qr_image'] = qr

            tournament = request.env['auction.tournament'].sudo().create(vals)

            # Create teams if organizer specified a team count
            try:
                team_count = int(post.get('team_count', 0) or 0)
            except (ValueError, TypeError):
                team_count = 0

            for i in range(1, team_count + 1):
                team_name = (post.get('team_name_%d' % i) or '').strip()
                if not team_name:
                    continue  # skip blank rows
                team_vals = {
                    'name': team_name,
                    'tournament_id': tournament.id,
                    'manager': (post.get('team_owner_%d' % i) or '').strip() or False,
                }
                team_logo = _read_file('team_logo_%d' % i)
                if team_logo:
                    team_vals['logo'] = team_logo
                request.env['auction.team'].sudo().create(team_vals)

            # PRG: redirect to GET so that page refreshes don't re-submit the form
            from urllib.parse import urlencode
            qs = urlencode({
                'success': '1',
                'name': tournament.name,
                'code': tournament.tournament_code or '—',
            })
            return werkzeug.utils.redirect('/tournament/register?' + qs, 303)

        except Exception as e:
            _logger.exception("Tournament registration failed")
            return request.render(
                'auction_module.tournament_registration_form',
                {
                    'db_name': db_name,
                    'success': False,
                    'error': str(e),
                    'sample_player_id': sample_player_id,
                    'res_company': res_company,
                }
            )

    # ── Jersey Collection Survey (auction_champ_jersy) ───────────────────────
    # Routes live here (not in auction_champ_jersy) so they are on the same
    # server-wide Auction controller as /player/register. Without a session
    # cookie, Odoo only matches auth='none' routes from server_wide_modules.

    _JERSEY_SLEEVES = {'F', 'H'}

    @staticmethod
    def _jersey_size_selection(env):
        if 'auction.champ.jersey.player' not in env:
            return []
        return env['auction.champ.jersey.player']._fields['size'].selection

    @classmethod
    def _jersey_size_codes(cls, env):
        return {code for code, _ in cls._jersey_size_selection(env)}

    @classmethod
    def _jersey_size_list(cls, env):
        return [code for code, _ in cls._jersey_size_selection(env)]

    def _resolve_db_for_jersey_slug(self, slug):
        """Return the database that has an active jersey team with *slug*."""
        from odoo.http import db_monodb, db_list
        mono = db_monodb(request.httprequest)
        candidates = []
        if mono:
            candidates.append(mono)
        try:
            for db in db_list(force=True, httprequest=request.httprequest):
                if db not in candidates:
                    candidates.append(db)
        except Exception:
            pass
        for db in candidates:
            try:
                registry = odoo.registry(db)
            except Exception:
                continue
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    if 'auction.champ.jersey.team' not in env:
                        continue
                    match = env['auction.champ.jersey.team'].sudo().search([
                        ('slug', '=', slug),
                        ('active', '=', True),
                    ], limit=1)
                    if match:
                        return db
            except Exception:
                continue
        return mono or (candidates[0] if candidates else None)

    def _jersey_img_url(self, db_name, team, field):
        rec = team.with_context(bin_size=False).sudo()
        if not rec[field]:
            return ''
        return '/%s/auction/public/image/auction.champ.jersey.team/%d/%s' % (
            db_name, team.id, field,
        )

    def _jersey_survey_values(self, db_name, team, **extra):
        players = team.player_ids.sorted(lambda p: p.id)
        size_selection = self._jersey_size_selection(team.env)
        return {
            'db_name': db_name,
            'team': team,
            'players': players,
            'player_count': len(players),
            'team_logo_uri': self._jersey_img_url(db_name, team, 'team_logo'),
            'sponsor_logo_uri': self._jersey_img_url(db_name, team, 'sponsor_logo'),
            'jersey_design_uri': self._jersey_img_url(db_name, team, 'jersey_design'),
            'size_options': size_selection,
            'size_labels': dict(size_selection),
            'error': extra.get('error'),
            'form': extra.get('form') or {},
            'success': extra.get('success', False),
            'ack_player': extra.get('ack_player'),
        }

    def _render_jersey_survey(self, db_name, team, **extra):
        html = request.render(
            'auction_champ_jersy.jersey_survey_template',
            self._jersey_survey_values(db_name, team, **extra),
            lazy=False,
        )
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/auction/jersey/<string:slug>', type='http', auth='none',
                website=False, methods=['GET', 'POST'], csrf=False)
    def jersey_survey_legacy(self, slug, **kw):
        """Redirect /auction/jersey/<slug> → /<db>/auction/jersey/<slug>."""
        db_name = self._resolve_db_for_jersey_slug(slug)
        if not db_name:
            return self._not_found()
        target = '/%s/auction/jersey/%s' % (db_name, slug)
        qs = request.httprequest.query_string
        if qs:
            target = '%s?%s' % (
                target, qs.decode('utf-8') if isinstance(qs, bytes) else qs,
            )
        return werkzeug.utils.redirect(target, 301)

    @http.route(
        '/<string:db_name>/auction/jersey/<string:slug>',
        type='http', auth='none', website=False,
        methods=['GET', 'POST'], csrf=False,
    )
    def jersey_survey(self, db_name, slug, **kw):
        """Public jersey collection form — same multi-db pattern as player register."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            if 'auction.champ.jersey.team' not in request.env:
                return self._not_found()

            team = request.env['auction.champ.jersey.team'].sudo().search([
                ('slug', '=', slug),
                ('active', '=', True),
            ], limit=1)
            if not team:
                return self._not_found()

            if request.httprequest.method == 'POST':
                return self._jersey_handle_submit(db_name, team, **kw)

            ack_player = None
            success = False
            if kw.get('submitted') == '1' and kw.get('entry'):
                try:
                    entry_id = int(kw.get('entry'))
                except (TypeError, ValueError):
                    entry_id = 0
                if entry_id:
                    player = request.env['auction.champ.jersey.player'].sudo().browse(entry_id)
                    if player.exists() and player.team_id.id == team.id:
                        ack_player = player
                        success = True

            return self._render_jersey_survey(
                db_name, team, success=success, ack_player=ack_player,
            )

    def _jersey_handle_submit(self, db_name, team, **kw):
        player_name = (kw.get('player_name') or '').strip()
        number = (kw.get('number') or '').strip()
        size = (kw.get('size') or '').strip().upper()
        sleeve = (kw.get('sleeve') or '').strip().upper()
        form = {
            'player_name': player_name,
            'number': number,
            'size': size,
            'sleeve': sleeve,
        }
        error = None
        if not player_name:
            error = 'Please enter the name to print on the jersey.'
        elif size not in self._jersey_size_codes(request.env):
            error = 'Please select a valid size.'
        elif sleeve not in self._JERSEY_SLEEVES:
            error = 'Please select sleeve type (Full or Half).'
        if error:
            return self._render_jersey_survey(db_name, team, error=error, form=form)

        player = request.env['auction.champ.jersey.player'].sudo().create({
            'team_id': team.id,
            'player_name': player_name,
            'number': number or False,
            'size': size,
            'sleeve': sleeve,
        })
        return werkzeug.utils.redirect(
            '/%s/auction/jersey/%s?submitted=1&entry=%d' % (
                db_name, team.slug, player.id,
            ),
            303,
        )


def _pj_player_photo_url(db_name, player, projector_size=True):
    """Public photo URL with write_date cache-buster (+ optional projector resize)."""
    if not player or not player.photo:
        return ''
    ver = ''
    if player.write_date:
        try:
            ver = str(int(fields.Datetime.from_string(player.write_date).timestamp()))
        except Exception:
            ver = str(player.write_date).replace(' ', 'T')
    else:
        ver = str(player.id)
    url = '/%s/auction/public/image/auction.team.player/%d/photo?v=%s' % (
        db_name, player.id, ver,
    )
    # sz=pj → smaller JPEG for the live stage card; remaining/squad use full photo
    if projector_size:
        url += '&sz=pj'
    return url


def _pj_progress(tournament, current_player=None):
    """Audience progress strip: Player X of Y (read-only, no state changes)."""
    if not tournament:
        return {'current': 0, 'total': 0, 'label': ''}
    Player = request.env['auction.team.player'].sudo()
    domain = [('tournament_id', '=', tournament.id), ('icon_player', '=', False)]
    total = Player.search_count(domain)
    done = Player.search_count(domain + [('state', 'in', ('sold', 'unsold'))])
    current = done
    if current_player:
        if current_player.state in ('sold', 'unsold'):
            current = max(done, 1)
        else:
            current = min(done + 1, total) if total else 0
    label = ('%s of %s' % (current, total)) if total else ''
    return {'current': current, 'total': total, 'label': label}


def _pj_wait_phase(tournament, audience='projector'):
    """Idle projector / live-board screen phase when no player is on stage.

    - about_to_begin: everyone still in draft (no sold/unsold/auction yet)
    - waiting: auction underway (someone sold/unsold, or a player in auction)
    - completed: declared complete, or nothing left in draft/auction

    ``audience``:
    - projector → owners / floor ceremony copy
    - viewers   → public live-board Thank You Viewers copy
    """
    name = (tournament.name or 'the tournament') if tournament else 'the tournament'
    if not tournament:
        return {
            'phase': 'about_to_begin',
            'tournament_name': name,
            'thanks_title': 'Thank You',
            'message': 'THE BATTLE FOR TALENT BEGINS SOON',
        }

    def _completed_payload():
        if audience == 'viewers':
            return {
                'phase': 'completed',
                'tournament_name': name,
                'thanks_title': 'Thank You Viewers',
                'message': (
                    'THANKS FOR STAYING TUNED TO THE AUCTION. '
                    'THE ROAD TO GLORY BEGINS.'
                ),
            }
        return {
            'phase': 'completed',
            'tournament_name': name,
            'thanks_title': 'Thank You',
            'message': 'THE AUCTION FLOOR CLOSES, AND THE ROAD TO GLORY BEGINS.',
        }

    # Operator "Declare Auction Complete" → Thank You ceremony
    if tournament.auction_declared_complete:
        return _completed_payload()
    Player = request.env['auction.team.player'].sudo()
    domain = [('tournament_id', '=', tournament.id), ('icon_player', '=', False)]
    draft = Player.search_count(domain + [('state', '=', 'draft')])
    auction = Player.search_count(domain + [('state', '=', 'auction')])
    sold = Player.search_count(domain + [('state', '=', 'sold')])
    unsold = Player.search_count(domain + [('state', '=', 'unsold')])
    remaining = draft + auction
    finished = sold + unsold

    if remaining == 0 and finished > 0:
        return _completed_payload()
    if auction == 0 and sold == 0 and unsold == 0:
        return {
            'phase': 'about_to_begin',
            'tournament_name': name,
            'thanks_title': 'Thank You',
            'message': 'THE BATTLE FOR TALENT BEGINS SOON',
        }
    return {
        'phase': 'waiting',
        'tournament_name': name,
        'thanks_title': 'Thank You',
        'message': 'THE SPOTLIGHT MOVES TO THE NEXT PLAYER',
    }


def _pj_boards(tournament, db_name):
    """Live pool/fixture board payload for the projector (+ snapshot URLs)."""
    empty = {
        'mode': 'idle',
        'revealing': False,
        'reveal_kind': '',
        'tournament_name': '',
        'pools': [],
        'row_count': 1,
        'fixture': False,
        'sig': '',
        'pool_draw_url': '',
        'fixture_url': '',
        'has_pools': False,
        'has_fixture': False,
    }
    if not tournament:
        return empty

    try:
        from datetime import datetime
        import pytz
        now_dt = datetime.now(pytz.utc).replace(tzinfo=None)

        # Defensive: module may not be upgraded yet
        mode = getattr(tournament, 'projector_board_mode', None) or 'idle'
        reveal_until = getattr(tournament, 'projector_board_reveal_until', None)
        # Thank You / auction-complete always overrides live pool & fixture boards
        try:
            if getattr(tournament, 'auction_declared_complete', False):
                mode = 'idle'
                reveal_until = None
            elif _pj_wait_phase(tournament).get('phase') == 'completed':
                mode = 'idle'
                reveal_until = None
        except Exception:
            pass
        pool_draw_json = getattr(tournament, 'pool_draw_json', None)
        fixture_schedule_json = getattr(tournament, 'fixture_schedule_json', None)
        pool_snap = getattr(tournament, 'pool_draw_snapshot', None)
        fix_snap = getattr(tournament, 'fixture_schedule_snapshot', None)

        ver = ''
        if tournament.write_date:
            try:
                from odoo import fields as odoo_fields
                ver = str(int(odoo_fields.Datetime.from_string(tournament.write_date).timestamp()))
            except Exception:
                ver = str(tournament.write_date).replace(' ', 'T')
        base = '/%s/auction/public/image/auction.tournament/%d' % (db_name, tournament.id)
        qs = ('?v=' + ver) if ver else ''
        pool_url = ('%s/pool_draw_snapshot%s' % (base, qs)) if pool_snap else ''
        fix_url = ('%s/fixture_schedule_snapshot%s' % (base, qs)) if fix_snap else ''

        revealing = bool(
            reveal_until and reveal_until > now_dt and mode in ('pools', 'fixtures')
        )

        pools = []
        tournament_name = tournament.name or ''
        fixture = False
        Wizard = request.env['auction.team.pool.wizard'].sudo()

        if pool_draw_json:
            try:
                raw = json.loads(pool_draw_json)
                structure = raw.get('structure') or []
                pool_names = raw.get('pool_names') or []
                pools, tname = Wizard._client_build_pools(structure, pool_names)
                if tname:
                    tournament_name = tname
            except Exception:
                pools = []

        if fixture_schedule_json:
            try:
                fixture = Wizard._client_refresh_fixture(json.loads(fixture_schedule_json))
                if fixture and not fixture.get('matches'):
                    fixture = False
            except Exception:
                fixture = False

        def _public_team(team_payload):
            """Rewrite auth-only /web/image logos to public projector URLs."""
            if not team_payload:
                return team_payload
            tid = team_payload.get('id')
            if tid and team_payload.get('logo_url'):
                team_payload = dict(team_payload)
                team_payload['logo_url'] = (
                    '/%s/auction/public/image/auction.team/%d/logo' % (db_name, int(tid))
                )
            return team_payload

        def _public_pools(pool_list):
            out = []
            for pool in pool_list or []:
                out.append({
                    'index': pool.get('index'),
                    'name': pool.get('name'),
                    'teams': [_public_team(dict(t)) for t in (pool.get('teams') or [])],
                })
            return out

        def _public_fixture(fx):
            if not fx:
                return False
            matches = []
            for m in fx.get('matches') or []:
                matches.append({
                    'group': m.get('group') or '',
                    'section': m.get('section') or '',
                    'team_a': _public_team(dict(m.get('team_a') or {})),
                    'team_b': _public_team(dict(m.get('team_b') or {})),
                })
            return {
                'tournament': fx.get('tournament') or '',
                'subtitle': fx.get('subtitle') or '',
                'fixture_type': fx.get('fixture_type') or '',
                'outside_n': fx.get('outside_n') or 1,
                'matches': matches,
            }

        live_pools = _public_pools(pools) if mode == 'pools' else []
        live_fixture = _public_fixture(fixture) if mode == 'fixtures' else False
        row_count = max(1, (len(live_pools) + 1) // 2) if live_pools else 1

        sig_parts = [
            mode,
            '1' if revealing else '0',
            str(reveal_until or ''),
            str(len(live_pools)),
            str(len((live_fixture or {}).get('matches') or []) if live_fixture else 0),
            ver,
            str(len(pools)),
            str(len((fixture or {}).get('matches') or []) if fixture else 0),
        ]
        return {
            'mode': mode if mode in ('pools', 'fixtures') else 'idle',
            'revealing': revealing,
            'reveal_kind': mode if revealing else '',
            'tournament_name': tournament_name,
            'pools': live_pools,
            'row_count': row_count,
            'fixture': live_fixture,
            'sig': '|'.join(sig_parts),
            'pool_draw_url': pool_url,
            'fixture_url': fix_url,
            'has_pools': bool(pools),
            'has_fixture': bool(fixture),
        }
    except Exception:
        # Never break the main projector poll
        return empty


def _pj_auction_meta(tournament):
    """Auction date/venue for the projector header (live-polled)."""
    if not tournament:
        return {'auction_date': '', 'auction_venue': ''}
    date_label = ''
    if tournament.auction_date:
        try:
            date_label = tournament.auction_date.strftime('%d %b %Y')
        except Exception:
            date_label = str(tournament.auction_date)
    return {
        'auction_date': date_label,
        'auction_venue': (tournament.auction_venue or '').strip(),
    }


def _pj_teams(tournament, db_name, leading_team_id=None):
    """Team logo strip + purse for the projector (read-only)."""
    if not tournament:
        return []
    purse_by_team = {}
    for auc in request.env['auction.auction'].sudo().search([('tournament_id', '=', tournament.id)]):
        if auc.team_id:
            purse_by_team[auc.team_id.id] = int(auc.remaining_points or 0)
    out = []
    for team in tournament.team_ids:
        logo_url = ''
        if team.logo:
            logo_url = '/%s/auction/public/image/auction.team/%d/logo' % (db_name, team.id)
        out.append({
            'id': team.id,
            'name': team.name or '',
            'logo_url': logo_url,
            'leading': bool(leading_team_id and team.id == leading_team_id),
            'remaining_points': purse_by_team.get(team.id, 0),
        })
    return out


def _pj_squad(tournament, db_name):
    """Full squad board: every team + sold/icon players (projector overlay)."""
    sport = (tournament.tournament_type or 'cricket') if tournament else 'cricket'
    if not tournament:
        return {'sport': sport, 'teams': []}

    Player = request.env['auction.team.player'].sudo()
    Auction = request.env['auction.auction'].sudo()
    AuctionPlayer = request.env['auction.auction.player'].sudo()
    sold_lines = AuctionPlayer.search(
        [('auction_id.tournament_id', '=', tournament.id)],
        order='create_date desc, id desc',
    )
    sold_rank = {}
    points_by_player = {}
    for idx, line in enumerate(sold_lines):
        if not line.player_id:
            continue
        pid = line.player_id.id
        if pid not in sold_rank:
            sold_rank[pid] = idx
        if pid not in points_by_player:
            points_by_player[pid] = int(line.points or 0)

    auctions_by_team = {}
    for auc in Auction.search([('tournament_id', '=', tournament.id)]):
        if auc.team_id:
            auctions_by_team[auc.team_id.id] = auc

    teams_out = []
    for team in tournament.team_ids.sorted('name'):
        logo_url = ''
        if team.logo:
            logo_url = '/%s/auction/public/image/auction.team/%d/logo' % (db_name, team.id)

        auction = auctions_by_team.get(team.id)
        max_players = int(auction.max_players or 0) if auction else 0
        total_purse = int(auction.total_point or 0) if auction else 0
        remaining_purse = int(auction.remaining_points or 0) if auction else 0
        # Recruited slots = auction squad lines (what max_players caps)
        recruited = len(auction.player_ids) if auction else 0
        spent_purse = max(total_purse - remaining_purse, 0)

        icon_ids = set(team.key_player_ids.ids) if team.key_player_ids else set()

        players = Player.search([
            ('tournament_id', '=', tournament.id),
            ('assigned_team_id', '=', team.id),
            '|', ('state', '=', 'sold'), ('icon_player', '=', True),
        ], order='sl_no asc, name asc')
        players = players.sorted(
            key=lambda p: (
                0 if p.state == 'sold' else 1,
                sold_rank.get(p.id, 10 ** 9) if p.state == 'sold' else int(p.sl_no or 10 ** 9),
                (p.name or '').lower(),
            )
        )

        players_out = []
        seen = set()
        for p in players:
            if p.id in seen:
                continue
            seen.add(p.id)
            mystery_hidden = bool(
                p.tier_id and p.tier_id.mystery and not p.mystery_revealed)
            if mystery_hidden:
                name = '???'
                photo_url = ''
            else:
                name = p.name or ''
                # Full-resolution photos for Team Showcase / squad overlays
                photo_url = _pj_player_photo_url(db_name, p, projector_size=False)
            if sport == 'football':
                role = (p.dominant_position_id.name if p.dominant_position_id else '') or ''
            else:
                role = p.role or ''
            jersey = ''
            if not mystery_hidden:
                jersey_raw = (getattr(p, 'jersy_number', None) or '').strip()
                if jersey_raw:
                    try:
                        jersey = '%02d' % int(jersey_raw)
                    except (TypeError, ValueError):
                        jersey = jersey_raw[:4]
            is_icon = bool(p.icon_player) or (p.id in icon_ids)
            players_out.append({
                'id': p.id,
                'name': name,
                'photo_url': photo_url,
                'role': role,
                'jersey': jersey,
                'sl_no': 0 if mystery_hidden else int(p.sl_no or 0),
                'tier_name': (p.tier_id.name if p.tier_id and not mystery_hidden else '') or '',
                'tier_color': (p.tier_id.color if p.tier_id else '') or '#888',
                'is_icon': is_icon,
                'points': 0 if is_icon else int(points_by_player.get(p.id, 0) or 0),
            })

        # Icons first for stable showcase ordering
        players_out.sort(key=lambda pl: (0 if pl.get('is_icon') else 1, (pl.get('name') or '').lower()))

        teams_out.append({
            'id': team.id,
            'auction_id': auction.id if auction else False,
            'name': team.name or '',
            'logo_url': logo_url,
            'count': recruited,
            'max_players': max_players,
            'total_purse': total_purse,
            'remaining_purse': remaining_purse,
            'spent_purse': spent_purse,
            'players': players_out,
        })
    return {'sport': sport, 'teams': teams_out}


def _pj_remaining_players(tournament, db_name):
    """Remaining ``auction``-state players for the projector (kanban-style cards).

    Mirrors ``auction.team.player`` kanban fields/logic:
    photo, name, #, tier, role/position, category, and sport-specific stats.
    """
    sport = (tournament.tournament_type or 'cricket') if tournament else 'cricket'
    if not tournament:
        return {'sport': sport, 'count': 0, 'players': []}

    players = request.env['auction.team.player'].sudo().search([
        ('tournament_id', '=', tournament.id),
        ('icon_player', '=', False),
        ('state', '=', 'auction'),
    ], order='sl_no asc, name asc')

    out = []
    for p in players:
        mystery_hidden = bool(
            (getattr(p, 'is_mystery', False) or (p.tier_id and p.tier_id.mystery))
            and not p.mystery_revealed
        )
        fb = _football_display_payload(p)
        if mystery_hidden:
            photo_url = ''
            name = 'Mystery Player'
            sl_no = 0
            tier_name = 'Mystery'
            role = '???'
            batting = ''
            bowling = ''
            dominant_position = '???'
            preferred_foot = ''
            age = ''
            p_category = ''
            blood_group = ''
            location = ''
            other_attributes = []
            use_other_attributes = False
        else:
            # Full photo (no sz=pj) so remaining-player cards stay sharp/reliable
            photo_url = _pj_player_photo_url(db_name, p, projector_size=False)
            name = p.name or ''
            sl_no = int(p.sl_no or 0)
            tier_name = (p.tier_id.name if p.tier_id else '') or ''
            role = p.role or ''
            batting = p.batting_style or ''
            bowling = p.bowling_style or ''
            dominant_position = fb.get('dominant_position') or ''
            preferred_foot = fb.get('preferred_foot') or ''
            age = fb.get('age') or ''
            p_category = p.p_category or fb.get('p_category') or ''
            blood_group = p.blood_group or fb.get('blood_group') or ''
            location = fb.get('location') or p.address or ''
            other_attributes = fb.get('other_attributes') or []
            use_other_attributes = bool(fb.get('use_other_attributes'))

        out.append({
            'id': p.id,
            'name': name,
            'sl_no': sl_no,
            'photo_url': photo_url,
            'tier_name': tier_name,
            'tier_color': (p.tier_id.color if p.tier_id else '') or '#888',
            'role': role,
            'batting_style': batting,
            'bowling_style': bowling,
            'dominant_position': dominant_position,
            'preferred_foot': preferred_foot,
            'age': age,
            'p_category': p_category,
            'blood_group': blood_group,
            'location': location,
            'other_attributes': other_attributes,
            'use_other_attributes': use_other_attributes,
            'is_mystery': mystery_hidden,
        })

    return {'sport': sport, 'count': len(out), 'players': out}


def _pj_advertisers(tournament, db_name):
    """Sponsor logos for projector break-time slider."""
    if not tournament:
        return []
    out = []
    for ad in tournament.advertiser_ids:
        if not ad.image:
            continue
        out.append({
            'id': ad.id,
            'name': ad.name or '',
            'image_url': '/%s/auction/public/image/auction.advertiser/%d/image' % (db_name, ad.id),
        })
    return out


def _pj_top_purse(tournament):
    """Highest remaining purse among teams (audience 'balance' readout)."""
    if not tournament:
        return {'amount': 0, 'team_name': '', 'team_logo_url': ''}
    best = None
    for auc in request.env['auction.auction'].sudo().search([('tournament_id', '=', tournament.id)]):
        if not auc.team_id:
            continue
        pts = int(auc.remaining_points or 0)
        if best is None or pts > best[0]:
            best = (pts, auc.team_id)
    if not best:
        return {'amount': 0, 'team_name': '', 'team_logo_url': ''}
    team = best[1]
    db_name = request.env.cr.dbname
    logo_url = ''
    if team.logo:
        logo_url = '/%s/auction/public/image/auction.team/%d/logo' % (db_name, team.id)
    return {
        'amount': best[0],
        'team_name': team.name or '',
        'team_logo_url': logo_url,
    }


def _pj_recent_bids(tournament, db_name, player=None):
    """Last 5 completed sales for the projector Recent Bidding rail.

    Each row: player photo + name, sold-to team logo + name, points.
    Mystery players stay masked until revealed.
    """
    out = []
    if not tournament:
        return out

    def _team_logo(team):
        if team and team.logo:
            return '/%s/auction/public/image/auction.team/%d/logo' % (db_name, team.id)
        return ''

    def _player_photo(p):
        if p and p.photo:
            return '/%s/auction/public/image/auction.team.player/%d/photo' % (db_name, p.id)
        return ''

    # Prefer structured sale lines (player + team + points)
    sales = request.env['auction.auction.player'].sudo().search(
        [('auction_id.tournament_id', '=', tournament.id)],
        order='id desc',
        limit=5,
    )
    for line in sales:
        p = line.player_id
        team = line.auction_id.team_id if line.auction_id else False
        name = (p.name or '') if p else ''
        photo = _player_photo(p)
        if p and p.tier_id and p.tier_id.mystery and not p.mystery_revealed:
            name = '???'
            photo = '/auction_module/static/img/default_icon.png'
        out.append({
            'player_name': name or '—',
            'player_photo_url': photo,
            'team_name': (team.name if team else '') or '—',
            'team_logo_url': _team_logo(team),
            'points': int(line.points or 0),
            'kind': 'sold',
        })
    if out:
        return out

    # Fallback: parse recent history rows that look like sales
    import re
    history = request.env['auction.history'].sudo().search(
        [('tournament_id', '=', tournament.id)], order='id desc', limit=12
    )
    for rec in history:
        if len(out) >= 5:
            break
        msg = (rec.message or '').lower()
        if 'sold' not in msg and 'unsold' not in msg:
            continue
        pts = 0
        m = re.search(r'for\s+(\d+)\s+points?', rec.message or '', re.I)
        if m:
            pts = int(m.group(1))
        p = rec.player_id
        team = rec.team_id
        name = (p.name or '') if p else ''
        photo = _player_photo(p)
        if not photo and rec.player_photo:
            photo = '/%s/auction/public/image/auction.history/%d/player_photo' % (db_name, rec.id)
        if p and p.tier_id and p.tier_id.mystery and not p.mystery_revealed:
            name = '???'
            photo = '/auction_module/static/img/default_icon.png'
        team_name = team.name if team else ''
        if not team_name and 'unsold' in msg:
            team_name = 'Unsold'
        out.append({
            'player_name': name or '—',
            'player_photo_url': photo,
            'team_name': team_name or '—',
            'team_logo_url': _team_logo(team),
            'points': pts,
            'kind': 'unsold' if 'unsold' in msg else 'sold',
        })
    return out


def _football_display_payload(player):
    """Return JSON-serializable sport attributes for projector / selector JS.

    Always returns a stable key set so clients can branch on ``tournament_type``
    without KeyErrors. Football-only fields are empty for cricket.
    """
    is_football = bool(player.tournament_id and player.tournament_id.tournament_type == 'football')
    foot_map = {'left': 'Left', 'right': 'Right', 'both': 'Both'}
    rate_map = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
    shared = {
        'tournament_type': (
            player.tournament_id.tournament_type if player.tournament_id else 'cricket'
        ),
        'p_category': player.p_category or '',
        'blood_group': player.blood_group or '',
        'mobile': player.masked_contact or '',
        'location': player.address or '',
        'age': player.age or '',
        'height': player.height or '',
        'weight': player.weight or '',
    }
    if not is_football:
        return {
            **shared,
            'dominant_position': '',
            'dominant_position_code': '',
            'secondary_positions': [],
            'preferred_foot': '',
            'work_rate': '',
            'playing_styles': [],
            'strengths': [],
            'other_attributes': [],
            'use_other_attributes': False,
        }
    other_attributes = [
        {'label': a.label or '', 'value': a.value or ''}
        for a in player.other_attribute_ids
        if a.label and (a.value or '').strip()
    ]
    use_other = bool(other_attributes)
    return {
        **shared,
        'tournament_type': 'football',
        'dominant_position': player.dominant_position_id.name if player.dominant_position_id else '',
        'dominant_position_code': player.dominant_position_id.code if player.dominant_position_id else '',
        'secondary_positions': [] if use_other else [p.code or p.name for p in player.secondary_position_ids],
        'preferred_foot': foot_map.get(player.preferred_foot, ''),
        'age': '' if use_other else (player.age or ''),
        'work_rate': '' if use_other else rate_map.get(player.work_rate, ''),
        'playing_styles': [] if use_other else [{'name': s.name, 'icon': s.icon or ''} for s in player.playing_style_ids],
        'strengths': [] if use_other else [{'name': s.name, 'icon': s.icon or ''} for s in player.strength_ids],
        'other_attributes': other_attributes,
        'use_other_attributes': use_other,
    }


def _build_player_vals_from_post(request, tournament):
    """Extract and validate POST form data into a dict for auction.team.player.create()."""
    post = request.httprequest.form
    files = request.httprequest.files

    name = (post.get('name') or '').strip()
    if not name:
        raise ValueError("Player name is required.")

    # Determine next sl_no scoped to this tournament so numbering restarts per event
    last = request.env['auction.team.player'].sudo().search(
        [('tournament_id', '=', tournament.id)] if tournament else [],
        limit=1, order='sl_no desc'
    )
    sl_no = (last.sl_no + 1) if last else 1

    tier_id = False
    raw_tier = post.get('tier_id')
    if raw_tier and raw_tier.isdigit():
        tier_id = int(raw_tier)

    # Photo upload — mandatory
    photo_data = False
    photo_file = files.get('photo')
    if photo_file and photo_file.filename:
        photo_data = base64.b64encode(photo_file.read())
    if not photo_data:
        raise ValueError("Player photo is required. Please upload a photo.")

    # Payment proof upload
    payment_proof_data = False
    proof_file = files.get('payment_proof')
    if proof_file and proof_file.filename:
        payment_proof_data = base64.b64encode(proof_file.read())
    if tournament and tournament.payment_proof_required and not payment_proof_data:
        raise ValueError(
            "Payment proof is required. Please upload a receipt or payment screenshot."
        )

    is_football = bool(tournament and tournament.tournament_type == 'football')

    vals = {
        'sl_no':         sl_no,
        'name':          name,
        'contact':       (post.get('contact') or '').strip(),
        'org_id':        (
            (post.get('org_id') or '').strip()
            if tournament and tournament.enable_org_id_registration
            else False
        ),
        'address':       (post.get('address') or '').strip(),
        'blood_group':   (post.get('blood_group') or '').strip(),
        'current_team':  (post.get('current_team') or '').strip(),
        'state':         'draft',
        'photo':         photo_data,
        'payment_proof': payment_proof_data,
    }

    # Optional email (added by overlay modules such as ac_whatsapp)
    email = (post.get('email') or '').strip()
    Player = request.env['auction.team.player']
    if email and 'email' in Player._fields:
        vals['email'] = email

    if is_football:
        # ── Football profile ────────────────────────────────────────────────
        raw_dom = post.get('dominant_position_id')
        if raw_dom and raw_dom.isdigit():
            vals['dominant_position_id'] = int(raw_dom)

        sec_ids = [int(v) for v in post.getlist('secondary_position_ids') if v.isdigit()]
        if sec_ids:
            vals['secondary_position_ids'] = [(6, 0, sec_ids)]

        style_ids = [int(v) for v in post.getlist('playing_style_ids') if v.isdigit()]
        if style_ids:
            vals['playing_style_ids'] = [(6, 0, style_ids)]

        strength_ids = [int(v) for v in post.getlist('strength_ids') if v.isdigit()]
        if strength_ids:
            vals['strength_ids'] = [(6, 0, strength_ids)]

        if post.get('preferred_foot'):
            vals['preferred_foot'] = post.get('preferred_foot')
        if post.get('work_rate'):
            vals['work_rate'] = post.get('work_rate')

        raw_age = post.get('age')
        if raw_age and raw_age.isdigit():
            vals['age'] = int(raw_age)
        vals['height'] = (post.get('height') or '').strip()
        vals['weight'] = (post.get('weight') or '').strip()
    else:
        # ── Cricket profile ─────────────────────────────────────────────────
        vals['role'] = post.get('role') or ''
        vals['batting_style'] = post.get('batting_style') or 'Right Handed'
        vals['bowling_style'] = post.get('bowling_style') or 'Right Arm'

    if tier_id:
        vals['tier_id'] = tier_id
    if tournament:
        vals['tournament_id'] = tournament.id

    # Jersey section (only if enabled for this tournament)
    if tournament and tournament.enable_jersey_section:
        vals['jersy_name']   = (post.get('jersy_name') or '').strip()
        vals['jersy_number'] = (post.get('jersy_number') or '').strip()
        vals['jersy_size']   = (post.get('jersy_size') or '').strip()
        if not vals['jersy_size']:
            raise ValueError("Jersey size is required. Please select a jersey size.")

    return vals
