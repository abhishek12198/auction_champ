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
            env = api.Environment(cr, SUPERUSER_ID, {})
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
        # Try to resolve tournament slug for redirect
        t_slug = ''
        try:
            with self._with_db(db_name) as ok:
                if ok:
                    tournament = request.env['auction.tournament'].sudo().search(
                        [('active', '=', True)], limit=1)
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
                tournament = request.env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1)
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
            html = request.render('auction_module.player_sequence_selector', {
                'tournament': tournament,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug or (tournament.slug if tournament else ''),
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
                'tier_color': p.tier_color or '',
                'state': p.state,
                'team_name': p.assigned_team_id.name if p.state == 'sold' and p.assigned_team_id else '',
                'team_logo': p.assigned_team_id.logo.decode('utf-8') if p.state == 'sold' and p.assigned_team_id and p.assigned_team_id.logo else '',
                'sold_points': points_map.get(p.id, 0) if p.state == 'sold' else 0,
            }
            for p in players
        ]

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
        },
        'auction.tournament': {'set_dice_state'},
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
        except Exception:
            pass

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

    @http.route(['''/<string:db_name>/<string:tournament_slug>/auction/show/team/balance'''], type='http', auth="none", website=False)
    def auction_team_balance(self, db_name, tournament_slug, **kwargs):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search([('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return self._not_found()
            domain = [('tournament_id', '=', tournament.id)]
            auctions = request.env['auction.auction'].sudo().search(domain)
            # Prefetch relations used by the balance page / max_call compute so
            # QWeb does not trigger per-team SQL while rendering list+grid+mobile.
            auctions.mapped('team_id')
            auctions.mapped('player_ids.tier_id')
            auctions.mapped('tier_limit_ids.tier_id')
            auctions.mapped('auction_bid_slab_ids')
            theme = tournament.player_display_template or 'vanilla'
            # Show internal actions (View Squad button) for any logged-in user
            access_type = 'internal' if request.session.uid else 'public'
            balance_template_map = {
                'pistah': 'auction_module.auction_details_show_pistah',
            }
            template_ref = balance_template_map.get(theme, 'auction_module.auction_details_show')
            html = request.render(template_ref, {
                'teams': auctions,
                'tournament': tournament,
                'type': access_type,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug,
            }, lazy=False)
        return request.make_response(html, [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'private, max-age=0, must-revalidate'),
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
            tournament = request.env['auction.tournament'].sudo().search([('slug', '=', tournament_slug)], limit=1)
            if not tournament:
                return request.make_response(
                    json.dumps({'error': 'tournament not found'}),
                    headers=[('Content-Type', 'application/json')]
                )
            domain = [('tournament_id', '=', tournament.id)]
            auctions = request.env['auction.auction'].sudo().search(domain)
            auctions.mapped('player_ids.tier_id')
            auctions.mapped('tier_limit_ids.tier_id')
            auctions.mapped('auction_bid_slab_ids')
            on_stage = request.env['auction.team.player'].sudo().search(
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
            exclude_id = kwargs.get('exclude', 0)

            # If no explicit "next player" request, resume the player already on stage
            if not exclude_id:
                on_stage_domain = [('is_on_stage', '=', True), ('state', '=', 'auction')]
                if tournament_id:
                    on_stage_domain.append(('tournament_id', '=', tournament_id.id))
                player = request.env['auction.team.player'].sudo().search(on_stage_domain, limit=1)
            else:
                player = None

            # No on-stage player (or caller wants next) → pick one
            if not player:
                player = request.env['auction.team.player'].sudo().get_random_player(
                    exclude_id=exclude_id,
                    tournament_id=tournament_id,
                )
            if player:
                auction_ids = request.env['auction.auction'].sudo().search(
                    [('tournament_id', '=', tournament_id.id)] if tournament_id else []
                )
                template_map = {
                    'vanilla':       'auction_module.player_template_new',
                    'butterscotch':  'auction_module.player_template_butterscotch',
                    'strawberry':    'auction_module.player_template_strawberry',
                    'cherry':        'auction_module.player_template_cherry',
                    'pistah':        'auction_module.player_template_pistah',
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
                }, lazy=False)
            else:
                theme = tournament_id.player_display_template if tournament_id else 'vanilla'
                t_domain = [('tournament_id', '=', tournament_id.id)] if tournament_id else [('id', '=', False)]
                # active_test=False so archived players still count for routing decisions
                Player = request.env['auction.team.player'].sudo().with_context(active_test=False)
                sold_count = Player.search_count(t_domain + [('state', '=', 'sold')])
                draft_count = Player.search_count(t_domain + [('state', '=', 'draft')])
                unsold_count = Player.search_count(t_domain + [('state', '=', 'unsold')])
                auction_ids = request.env['auction.auction'].sudo().search(
                    [('tournament_id', '=', tournament_id.id)] if tournament_id else []
                )
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
                # - Any Unsold left → Resume (even with 0 Sold)
                # - Draft left after some Sold → Resume
                # - Sold only (nothing left) → Thank You
                # - Draft only (auction never progressed) → Welcome
                if declared_done:
                    html = _thank_you_html()
                elif unsold_count > 0 or (draft_count > 0 and sold_count > 0):
                    html = request.render('auction_module.auction_resume_template', {
                        'tournament': tournament_id,
                        'theme': theme,
                        'db_name': db_name,
                        'draft_players': Player.search(
                            t_domain + [('state', '=', 'draft')],
                            order='sl_no asc, name asc',
                        ),
                        'unsold_players': Player.search(
                            t_domain + [('state', '=', 'unsold')],
                            order='sl_no asc, name asc',
                        ),
                        'draft_count': draft_count,
                        'unsold_count': unsold_count,
                        'sold_count': sold_count,
                        'auction_ids': auction_ids,
                    }, lazy=False)
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
        """Declare auction complete and go to the Thank You screen."""
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
                    tournament.sudo().write({'auction_declared_complete': True})
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

    def _team_players_render(self, team_id, tournament_slug=None, db_name=None):
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
        }
        template_ref = players_template_map.get(theme, 'auction_module.auction_team_players_template')
        resolved_slug = tournament_slug or (tournament.slug if tournament else '')
        ctx = {
            'players': player_data_list,
            'team': team,
            'tournament': tournament,
            'theme': theme,
            'db_name': db_name or request.env.cr.dbname,
            'tournament_slug': resolved_slug,
        }
        return template_ref, ctx

    @http.route('/auction/get/players/team/<int:team_id>', type='http', auth='public', website=True)
    def get_team_players(self, team_id):
        template_ref, ctx = self._team_players_render(team_id)
        return request.render(template_ref, ctx)

    @http.route('/<string:db_name>/auction/get/players/team/<int:team_id>',
                type='http', auth='none', website=False, sitemap=False)
    def get_team_players_db(self, db_name, team_id, **kwargs):
        """DB-aware variant so the roster loads on multi-database instances."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            template_ref, ctx = self._team_players_render(team_id, db_name=db_name)
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
                team_id, tournament_slug=tournament_slug, db_name=db_name)
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
            return request.redirect('/{}/{}/auction/live-board'.format(db_name, tournament.slug))
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

    @http.route('/auction/my/payment-marker', type='http', auth='user', website=False)
    def payment_marker_redirect(self, **kw):
        """Redirect the generic menu URL to the canonical /{db}/{slug}/auction/payment-marker URL."""
        has_access, is_admin = self._get_pm_access()
        if not has_access:
            return werkzeug.exceptions.Forbidden()

        env = request.env
        db_name = env.cr.dbname

        user_row = env.user.sudo().read(['tournament_id'])[0]
        tournament_id = user_row['tournament_id'][0] if user_row['tournament_id'] else None
        tournament_slug = None

        if tournament_id:
            t = env['auction.tournament'].sudo().browse(tournament_id).read(['slug'])[0]
            tournament_slug = t['slug'] or str(tournament_id)
        elif is_admin:
            t = env['auction.tournament'].sudo().search([('active', '=', True)], limit=1)
            if t:
                tournament_slug = t.slug or str(t.id)

        if not tournament_slug:
            return request.make_response(
                '<html><body style="font-family:sans-serif;padding:40px">'
                '<h2>No tournament assigned</h2>'
                '<p>Ask an administrator to assign a tournament to your user profile.</p>'
                '<a href="/web">&#8592; Back</a></body></html>',
                [('Content-Type', 'text/html; charset=utf-8')]
            )

        return werkzeug.utils.redirect(
            '/{}/{}/auction/payment-marker'.format(db_name, tournament_slug), 302
        )

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker',
                type='http', auth='none', website=False)
    def payment_marker_page(self, db_name, tournament_slug, **kw):
        """Render the Payment Tracker web page. Optimised: ≤5 DB hits regardless of player count.

        auth='none' so the route is reachable even when no database is selected
        (multi-db, logged-out). We then: (1) pin the URL's DB into the session so
        the login form binds to the right DB, (2) bounce anonymous users to the
        login screen, (3) elevate the request env to the logged-in user.
        """
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

        has_access, is_admin = self._get_pm_access()
        if not has_access:
            return werkzeug.exceptions.Forbidden()

        env = request.env

        # ── 1 DB: resolve tournament by slug ────────────────────────────
        tournament = env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )
        if not tournament:
            return self._not_found()
        tournament_id = tournament.id

        # Scope check: non-admins must belong to this tournament
        if not is_admin:
            user_row = env.user.sudo().read(['tournament_id'])[0]
            user_tourn_id = user_row['tournament_id'][0] if user_row['tournament_id'] else None
            if user_tourn_id != tournament_id:
                return werkzeug.exceptions.Forbidden()

        # ── 2 DB: ONE search_read for all players ───────────────────────
        PLAYER_FIELDS = [
            'id', 'sl_no', 'name', 'role', 'contact',
            'state', 'amount_paid', 'payment_url',
            'assigned_team_id', 'tier_id', 'payment_proof',
        ]
        rows = env['auction.team.player'].sudo().search_read(
            [('tournament_id', '=', tournament_id)],
            fields=PLAYER_FIELDS,
            order='sl_no asc, name asc',
        )

        # ── Auto-mark: filter in Python, one batch write if needed (0–1 DB) ──
        to_mark_ids = [r['id'] for r in rows if r['payment_url'] and not r['amount_paid']]
        if to_mark_ids:
            env['auction.team.player'].sudo().browse(to_mark_ids).write({'amount_paid': True})
            mark_set = set(to_mark_ids)
            for r in rows:
                if r['id'] in mark_set:
                    r['amount_paid'] = True

        # ── 3 DB: batch-read all unique teams (name, manager, logo) ────────
        team_ids = list({r['assigned_team_id'][0] for r in rows if r['assigned_team_id']})
        teams_map = {}
        if team_ids:
            for t in env['auction.team'].sudo().browse(team_ids).read(['id', 'name', 'manager', 'logo']):
                teams_map[t['id']] = {
                    'name':     t['name'] or '',
                    'manager':  t['manager'] or '',
                    'has_logo': bool(t['logo']),
                }

        # ── 4: Build proof data URIs from payment_proof field (ORM handles attachment lookup) ──
        def _proof_data_uri(b64_val):
            """Resize proof image to thumbnail and return data URI. b64_val is base64 bytes from ORM."""
            if not b64_val:
                return ''
            try:
                raw = base64.b64decode(b64_val)
                from PIL import Image as PILImage
                import io as _io
                img = PILImage.open(_io.BytesIO(raw))
                img.thumbnail((900, 1200), PILImage.LANCZOS)
                buf = _io.BytesIO()
                img.save(buf, format='JPEG', quality=82, optimize=True)
                return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
            except Exception:
                return 'data:image/jpeg;base64,' + (b64_val if isinstance(b64_val, str) else b64_val.decode('ascii'))

        # ── Mask contact in Python (skip ORM computed-field overhead) ────
        def _mask(c):
            c = str(c or '')
            return (c[0] + 'X' * (len(c) - 2) + c[-1]) if len(c) > 2 else c

        # ── Build players_data — zero DB from here ───────────────────────
        STATE_LABELS = {'draft': 'Draft', 'auction': 'In Auction', 'sold': 'Sold', 'unsold': 'Unsold'}
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
                'proof_att_id':      1 if r['payment_proof'] else 0,
                'proof_data':        _proof_data_uri(r['payment_proof']),
                'team':              team.get('name', ''),
                'manager':           team.get('manager', ''),
                'tier':              r['tier_id'][1] if r['tier_id'] else '',
            })

        # ── Stats: single pass ───────────────────────────────────────────
        total = len(players_data)
        paid_total = 0
        by_state = {st: [0, 0] for st in ('draft', 'auction', 'sold', 'unsold')}
        for p in players_data:
            if p['amount_paid']:
                paid_total += 1
            bucket = by_state.get(p['state'])
            if bucket:
                bucket[0] += 1
                if p['amount_paid']:
                    bucket[1] += 1
        stats = {
            'total':    total,
            'paid':     paid_total,
            'unpaid':   total - paid_total,
            'by_state': {st: {'total': v[0], 'paid': v[1]} for st, v in by_state.items()},
        }

        # ── Teams for filter chips — derived from teams_map (no extra DB) ─
        teams_data = sorted(
            [{'id': tid, 'name': t['name'], 'has_logo': t['has_logo']}
             for tid, t in teams_map.items()],
            key=lambda t: t['name'],
        )

        # ── 5 DB: company ────────────────────────────────────────────────
        company = env['res.company'].sudo().search([], limit=1)

        toggle_url = '/{}/{}/auction/payment-marker/toggle'.format(db_name, tournament_slug)
        proof_base_url = '/{}/{}/auction/payment-marker/proof/'.format(db_name, tournament_slug)
        upload_url = '/{}/{}/auction/payment-marker/upload-proof'.format(db_name, tournament_slug)
        unlink_url = '/{}/{}/auction/payment-marker/unlink-proof'.format(db_name, tournament_slug)

        html = request.render('auction_module.payment_marker_template', {
            'tournament':     tournament,
            'players_json':   self._safe_json(players_data),
            'stats_json':     self._safe_json(stats),
            'teams_json':     self._safe_json(teams_data),
            'toggle_url':     toggle_url,
            'proof_base_url': proof_base_url,
            'upload_url':     upload_url,
            'unlink_url':     unlink_url,
            'is_admin':       is_admin,
            'res_company':    company,
        }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/payment-marker/toggle',
                type='json', auth='user', website=False, csrf=False)
    def payment_marker_toggle(self, db_name, tournament_slug, player_id, paid, **kw):
        """Toggle amount_paid on a player. ≤3 DB hits (access cached, one read, one write)."""
        has_access, is_admin = self._get_pm_access()
        if not has_access:
            return {'error': 'Access denied'}
        try:
            pid = int(player_id)
            env = request.env

            # Resolve tournament by slug (scope anchor)
            tourn = env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tourn:
                return {'error': 'Tournament not found'}

            # One read: verify player exists and belongs to this tournament
            rows = env['auction.team.player'].sudo().search_read(
                [('id', '=', pid), ('tournament_id', '=', tourn.id)],
                ['id'], limit=1
            )
            if not rows:
                return {'error': 'Player not found'}

            # Scope check for non-admins
            if not is_admin:
                user_row = env.user.sudo().read(['tournament_id'])[0]
                user_tourn_id = user_row['tournament_id'][0] if user_row['tournament_id'] else None
                if user_tourn_id != tourn.id:
                    return {'error': 'Access denied — wrong tournament'}

            new_val = bool(paid)
            env['auction.team.player'].sudo().browse(pid).write({'amount_paid': new_val})
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

        player = env['auction.team.player'].sudo().search(
            [('id', '=', player_id), ('tournament_id', '=', tournament.id)], limit=1
        )
        if not player:
            return _json({'error': 'Player not found'})

        file_bytes = upload_file.read()
        # Binary field expects base64-encoded string, not bytes
        b64_str = base64.b64encode(file_bytes).decode('ascii')

        player.write({
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

        player = env['auction.team.player'].sudo().search(
            [('id', '=', player_id), ('tournament_id', '=', tournament.id)], limit=1
        )
        if not player:
            return _json({'error': 'Player not found'})

        # Clear the binary field — Odoo will delete the ir.attachment automatically
        player.write({'payment_proof': False})

        return _json({'success': True})

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
        slug = kw.get('t', '')
        target = '/{}/auction/player_selector/{}'.format(db_name, slug + '/' if slug else '')
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
                tournament = request.env['auction.tournament'].sudo().search(
                    [('active', '=', True)], limit=1)
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
            html = request.render('auction_module.player_sequence_selector', {
                'tournament': tournament,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug or (tournament.slug if tournament else ''),
            }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

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
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
            sport = (tournament.tournament_type or 'cricket') if tournament else 'cricket'
            html = request.render('auction_module.projector_template', {
                'tournament': tournament,
                'theme': theme,
                'sport': sport,
                'db_name': db_name,
                'tournament_slug': tournament_slug or (tournament.slug if tournament else ''),
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
            player = None
            state_override = None
            if (tournament and tournament.stamp_expires_at
                    and tournament.stamp_expires_at > now_dt
                    and tournament.stamp_player_id):
                player = tournament.stamp_player_id
                state_override = tournament.stamp_state
            if not player:
                domain = [('is_on_stage', '=', True)]
                if tournament:
                    domain.append(('tournament_id', '=', tournament.id))
                player = request.env['auction.team.player'].sudo().search(domain, limit=1)
            if not player:
                return {
                    'player': None,
                    'dice': {
                        'state': tournament.dice_state if tournament else 'idle',
                        'result': tournament.dice_result if tournament else 0,
                    },
                }
            photo = ''
            photo_url = ''
            if player.photo:
                photo_url = '/%s/auction/public/image/auction.team.player/%d/photo' % (
                    db_name, player.id)
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
            }
            player_payload.update(_football_display_payload(player))
            return {
                'player': player_payload,
                'dice': {'state': 'idle', 'result': 0},
            }

    @http.route('/auction/showcase', type='http', auth='user', website=True)
    def auction_showcase(self, **kw):
        """Redirect to the correct player showcase based on tournament algorithm."""
        tournament = self._resolve_tournament()
        if tournament and tournament.slug:
            db_name = request.env.cr.dbname
            if tournament.player_appearance_algorithm == 'linear':
                return request.redirect('/{}/auction/player_selector/{}/'.format(db_name, tournament.slug))
            return request.redirect('/{}/auction/display_auction/{}/'.format(db_name, tournament.slug))
        if tournament and tournament.player_appearance_algorithm == 'linear':
            return request.redirect('/auction/player_selector')
        return request.redirect('/auction/display_auction')

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
        'auction.tournament':  ['logo'],
        'auction.history':     ['player_photo'],
        'auction.advertiser':  ['image'],
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
        return 'image/jpeg'

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

        image_bytes = base64.b64decode(binary)
        return request.make_response(image_bytes, headers=[
            ('Content-Type', self._image_mimetype(image_bytes)),
            ('Cache-Control', 'public, max-age=300'),  # 5-min browser cache
        ])

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

            image_bytes = base64.b64decode(binary)
        return request.make_response(image_bytes, headers=[
            ('Content-Type', self._image_mimetype(image_bytes)),
            ('Cache-Control', 'public, max-age=300'),
        ])

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

    @http.route('/<string:db_name>/<string:tournament_slug>/auction/live-board', type='http', auth='none', website=False)
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
            }

            if tournament:
                result['theme'] = tournament.player_display_template or 'vanilla'
                result['break_time'] = tournament.break_time_active
                result['advertisers'] = [
                    {
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
                }
                result['current_player'].update(_football_display_payload(current_player))

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
            result['recent_history'] = [
                {
                    'message': rec.message or '',
                    'team_logo_url': pub_img('auction.team', rec.team_id.id, 'logo') if rec.team_id and rec.team_id.logo else '',
                    'player_photo_url': pub_img('auction.history', rec.id, 'player_photo') if rec.player_photo else '',
                    'timestamp': rec.create_date.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata')).strftime('%I:%M %p') if rec.create_date else '',
                }
                for rec in history
            ]

            # ── Top 5 most expensive sold players (MVP board) ──
            top_sold = env['auction.auction.player'].sudo().search(
                [('auction_id.tournament_id', '=', tournament.id)], order='points desc', limit=5
            )
            result['top_players'] = [
                {
                    'rank': idx + 1,
                    'player_name': rec.player_id.name or '',
                    'player_photo_url': pub_img('auction.team.player', rec.player_id.id, 'photo') if rec.player_id and rec.player_id.photo else '',
                    'role': rec.player_id.role or '',
                    'team_name': rec.auction_id.team_id.name if rec.auction_id and rec.auction_id.team_id else '',
                    'team_logo_url': pub_img('auction.team', rec.auction_id.team_id.id, 'logo') if rec.auction_id and rec.auction_id.team_id and rec.auction_id.team_id.logo else '',
                    'points': rec.points,
                }
                for idx, rec in enumerate(top_sold)
            ]

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
                        players_payload.append({
                            'name': p.name or '',
                            'photo_url': pub_img('auction.team.player', p.id, 'photo')
                                         if p.photo else '',
                            'role': p.role or '',
                            'position_code': pos_code,
                            'position_name': pos_name,
                            'points': line.points,
                        })
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

        # ── Tournament scope: only Auction Admin sees all; others → assigned tournaments
        is_admin = request.env.user.has_group('auction_module.group_auction_group_admin')
        user = request.env.user
        # Prefer Active Tournament; fall back to Organizers M2M so counts match list views
        user_tournament = user.tournament_id or user.tournament_ids[:1]
        allowed_tids = set(user.tournament_ids.ids)
        if user.tournament_id:
            allowed_tids.add(user.tournament_id.id)
        if is_admin:
            t_domain = []
        elif allowed_tids:
            t_domain = [('tournament_id', 'in', list(allowed_tids))]
        else:
            # No tournament assigned → show nothing (do not leak all tournaments)
            t_domain = [('id', '=', False)]

        # ── State counts ──────────────────────────────────────────────────────
        states = ['draft', 'auction', 'sold', 'unsold']
        state_counts = {s: Player.search_count(t_domain + [('state', '=', s)]) for s in states}
        total = sum(state_counts.values())

        # ── Last 10 draft players ─────────────────────────────────────────────
        last_draft = Player.search(t_domain + [('state', '=', 'draft')], order='create_date desc', limit=10)
        draft_players = []
        for p in last_draft:
            draft_players.append({
                'name':        p.name or '',
                'role':        p.role or '',
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

        # ── Role distribution ─────────────────────────────────────────────────
        all_players = Player.search(t_domain)
        role_counts = {}
        for p in all_players:
            role = (p.role or 'Unknown').strip() or 'Unknown'
            role_counts[role] = role_counts.get(role, 0) + 1
        roles = [{'label': k, 'count': v} for k, v in sorted(role_counts.items(), key=lambda x: -x[1])]

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
            icon_list.append({
                'name':      p.name or '',
                'role':      p.role or '',
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
            'tiers':             tiers,
            'team_player_counts': team_player_counts,
            'icon_players':      icon_list,
            'tournament_id':     user_tournament.id if user_tournament else None,
            'view_ids': {
                'kanban': _ref('view_auction_team_player_kanban'),
                'list':   _ref('view_auction_team_player_tree'),
            },
        }
        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        )

    # ── Squad Poster ──────────────────────────────────────────────────────────

    @http.route('/auction/squad-poster/<int:auction_id>', type='http', auth='user', website=False, csrf=False)
    def squad_poster_page(self, auction_id, **kw):
        """Renders a full-page IPL-style squad poster that auto-downloads as a high-res JPG."""
        env = request.env
        auction = env['auction.auction'].sudo().browse(auction_id)
        if not auction.exists():
            return request.not_found()

        team       = auction.team_id
        tournament = auction.tournament_id

        def b64uri(binary):
            if not binary:
                return ''
            raw = binary if isinstance(binary, str) else binary.decode('utf-8')
            return 'data:image/png;base64,' + raw

        # ── Palette ──────────────────────────────────────────────────────────
        DARK  = '#020c1b'
        NAVY  = '#0d1b3e'
        NAVY2 = '#16213e'
        NAVY3 = '#0a0f1e'   # icon-section bg
        GOLD  = '#E8A020'
        GOLD2 = '#F5C842'
        WHITE = '#FFFFFF'
        LIGHT = '#f0f4f8'   # squad section bg
        CARD  = '#FFFFFF'

        # ── Role colours ─────────────────────────────────────────────────────
        ROLE_CLR = {
            'batter':         '#1a7f37',
            'batsman':        '#1a7f37',
            'bowler':         '#1565C0',
            'all rounder':    '#E65100',
            'allrounder':     '#E65100',
            'all-rounder':    '#E65100',
            'wicket keeper':  '#6A1B9A',
            'wicketkeeper':   '#6A1B9A',
            'wicket-keeper':  '#6A1B9A',
            'wk':             '#6A1B9A',
        }

        def rc(role):
            lo = (role or '').lower().strip()
            return next((v for k, v in ROLE_CLR.items() if k in lo), '#374151')

        # ── Data ─────────────────────────────────────────────────────────────
        team_logo_src  = b64uri(team.logo)
        tourn_logo_src = b64uri(tournament.logo) if tournament and tournament.logo else ''
        icon_players    = list(team.key_player_ids)
        icon_ids        = set(team.key_player_ids.ids)
        regular_players = [p for p in auction.player_ids if p.player_id.id not in icon_ids]
        total_players   = len(icon_players) + len(regular_players)

        # ── Photo helpers ─────────────────────────────────────────────────────
        def tp_photo(p, size):
            """Square photo for auction.team.player (icon player)."""
            src = b64uri(p.photo)
            if src:
                return (
                    '<div style="width:%(s)dpx;height:%(s)dpx;border-radius:8px;'
                    'overflow:hidden;margin:0 auto;">'
                    '<img src="%(src)s" style="width:100%%;height:100%%;object-fit:contain;background:%(bg)s;">'
                    '</div>'
                ) % {'s': size, 'src': src, 'bg': LIGHT}
            initials = ''.join(w[0] for w in (p.name or 'P').split()[:2]).upper()
            return (
                '<div style="width:%(s)dpx;height:%(s)dpx;border-radius:8px;overflow:hidden;'
                'margin:0 auto;background:%(n)s;display:flex;align-items:center;'
                'justify-content:center;font-size:%(fs)dpx;color:%(g)s;font-weight:900;">%(i)s</div>'
            ) % {'s': size, 'n': NAVY, 'fs': size // 3, 'g': GOLD2, 'i': initials}

        def ap_photo(p, size):
            """Square photo for auction.auction.player (regular squad player)."""
            src = b64uri(p.player_id.photo)
            color = rc(p.player_id.role or '')
            if src:
                return (
                    '<div style="width:%(s)dpx;height:%(s)dpx;border-radius:8px;overflow:hidden;'
                    'margin:0 auto;border:3px solid %(c)s;'
                    'box-shadow:0 4px 12px %(c)s33;">'
                    '<img src="%(src)s" style="width:100%%;height:100%%;object-fit:cover;">'
                    '</div>'
                ) % {'s': size, 'c': color, 'src': src}
            initials = ''.join(w[0] for w in (p.player_id.name or 'P').split()[:2]).upper()
            return (
                '<div style="width:%(s)dpx;height:%(s)dpx;border-radius:8px;overflow:hidden;'
                'margin:0 auto;background:%(bg)s;border:3px solid %(c)s;'
                'display:flex;align-items:center;justify-content:center;'
                'font-size:%(fs)dpx;color:%(c)s;font-weight:900;">%(i)s</div>'
            ) % {'s': size, 'bg': LIGHT, 'c': color, 'fs': size // 3, 'i': initials}

        # ══════════════════════════════════════════════════════════════════════
        # LANDSCAPE POSTER — Left hero panel + right squad content
        # ══════════════════════════════════════════════════════════════════════

        # AuctionChamp app logo (white SVG)
        _logo_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'assets', 'images', 'logo.svg')
        try:
            with open(_logo_path, 'rb') as _lf:
                app_logo_src = 'data:image/svg+xml;base64,' + base64.b64encode(_lf.read()).decode('utf-8')
        except Exception:
            app_logo_src = ''

        tourn_name = (tournament.name or '') if tournament else ''
        tourn_desc = (tournament.description or '') if tournament else ''

        # Tournament logo HTML
        if tourn_logo_src:
            tlogo_html = '<img src="%(src)s" style="width:100%%;height:100%%;object-fit:contain;">' % {'src': tourn_logo_src}
        else:
            tlogo_html = '<span style="color:%(g)s;font-size:48px;">&#127942;</span>' % {'g': GOLD}

        # ── SECTION 1: LEFT HERO PANEL (Tournament info, 480px wide) ─────────────
        tourn_section = (
            '<div style="flex:0 0 480px;background:%(n)s;'
            'background-image:repeating-linear-gradient(45deg,rgba(255,255,255,0.025) 0,rgba(255,255,255,0.025) 2px,transparent 2px,transparent 24px);'
            'padding:36px 32px;display:flex;flex-direction:column;align-items:center;justify-content:center;'
            'position:relative;overflow:hidden;border-right:2px solid rgba(232,160,32,0.25);">'

            # Decorative circles in background
            '<div style="position:absolute;top:-80px;right:-80px;width:260px;height:260px;'
            'border-radius:50%%;border:1px solid rgba(232,160,32,0.12);"></div>'
            '<div style="position:absolute;bottom:-100px;left:-100px;width:300px;height:300px;'
            'border-radius:50%%;border:1px solid rgba(232,160,32,0.10);"></div>'

            # AuctionChamp logo badge (top-right corner)
            '<div style="position:absolute;top:16px;right:16px;'
            'display:flex;align-items:center;gap:6px;'
            'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);'
            'border-radius:20px;padding:6px 12px;">'
            '<img src="%(al)s" style="height:16px;width:auto;opacity:0.9;">'
            '</div>'

            # Tournament logo (large, centered)
            '<div style="width:140px;height:140px;border-radius:50%%;'
            'background:linear-gradient(135deg,%(g)s,%(g2)s);padding:4px;'
            'margin-bottom:24px;box-shadow:0 0 40px %(g)s77;">'
            '<div style="width:100%%;height:100%%;border-radius:50%%;overflow:hidden;'
            'background:%(n)s;">%(tlogo)s</div>'
            '</div>'

            # Tournament name
            '<div style="color:%(w)s;font-size:32px;font-weight:900;text-align:center;'
            'letter-spacing:2px;text-transform:uppercase;line-height:1.1;'
            'text-shadow:0 2px 20px rgba(0,0,0,0.4);margin-bottom:12px;">%(tn)s</div>'

            # Description
            '<div style="color:rgba(255,255,255,0.75);font-size:14px;text-align:center;'
            'letter-spacing:1px;font-style:italic;margin-bottom:20px;line-height:1.4;">%(desc)s</div>'

            # Gold divider
            '<div style="width:100px;height:2px;background:linear-gradient(90deg,transparent,%(g)s,%(g2)s,%(g)s,transparent);'
            'margin:0 auto 20px;border-radius:1px;"></div>'

            # Subtitle
            '<div style="color:%(g)s;font-size:10px;font-weight:bold;letter-spacing:6px;'
            'text-transform:uppercase;opacity:0.85;">OFFICIAL SQUAD</div>'

            '</div>'
        ) % {'n': NAVY, 'g': GOLD, 'g2': GOLD2, 'w': WHITE, 'al': app_logo_src,
             'tlogo': tlogo_html, 'tn': tourn_name, 'desc': tourn_desc}

        # ── SECTION 2: TEAM INFO & SQUAD (right side, 1440px wide) ──────────────
        right_container_start = (
            '<div style="flex:1;display:flex;flex-direction:column;'
            'overflow:hidden;min-width:0;">'
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 2 — Team Banner
        # ══════════════════════════════════════════════════════════════════════
        if team_logo_src:
            tl_el = (
                '<div style="width:120px;height:120px;border-radius:12px;'
                'background:linear-gradient(135deg,%(g)s,%(g2)s);padding:4px;flex-shrink:0;'
                'box-shadow:0 0 30px %(g)s55;">'
                '<div style="width:100%%;height:100%%;border-radius:10px;overflow:hidden;'
                'background:%(n)s;padding:8px;">'
                '<img src="%(src)s" style="width:100%%;height:100%%;object-fit:contain;">'
                '</div></div>'
            ) % {'g': GOLD, 'g2': GOLD2, 'n': NAVY2, 'src': team_logo_src}
        else:
            initial = (team.name or 'T')[0].upper()
            tl_el = (
                '<div style="width:120px;height:120px;border-radius:12px;'
                'background:linear-gradient(135deg,%(g)s,%(g2)s);flex-shrink:0;'
                'display:flex;align-items:center;justify-content:center;'
                'font-size:52px;color:%(n)s;font-weight:900;'
                'box-shadow:0 0 30px %(g)s55;">%(i)s</div>'
            ) % {'g': GOLD, 'g2': GOLD2, 'n': NAVY2, 'i': initial}

        team_name    = team.name or ''
        team_name_fs = max(24, min(46, 46 - max(0, len(team_name) - 14)))

        team_section = (
            '<div style="flex:0 0 auto;background:linear-gradient(90deg,%(n)s 0%%,%(n2)s 100%%);'
            'border-bottom:2px solid %(g)s;padding:28px 32px;display:flex;align-items:center;gap:28px;">'

            '%(tl)s'

            '<div style="flex:1;min-width:0;">'
            '<div style="color:%(g)s;font-size:11px;font-weight:bold;letter-spacing:6px;'
            'text-transform:uppercase;margin-bottom:6px;opacity:0.85;">SQUAD ANNOUNCEMENT</div>'
            '<div style="color:%(w)s;font-size:28px;font-weight:900;letter-spacing:1px;'
            'text-transform:uppercase;line-height:1.1;margin-bottom:6px;">%(nm)s</div>'
            '<div style="color:rgba(255,255,255,0.7);font-size:13px;">Owner: %(owner)s</div>'
            '</div>'

            '<div style="text-align:center;background:rgba(232,160,32,0.12);'
            'border:1px solid rgba(232,160,32,0.35);border-radius:14px;'
            'padding:16px 24px;flex-shrink:0;">'
            '<div style="color:%(g)s;font-size:36px;font-weight:900;">%(tp)d</div>'
            '<div style="color:rgba(255,255,255,0.6);font-size:9px;letter-spacing:2px;'
            'text-transform:uppercase;margin-top:4px;">PLAYERS</div>'
            '</div>'

            '</div>'
        ) % {'n': NAVY, 'n2': NAVY2, 'g': GOLD, 'w': WHITE,
             'tl': tl_el, 'nm': team.name or '', 'owner': (team.manager or 'N/A'),
             'tp': total_players}

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 3 — Icon Players (compact horizontal row)
        # ══════════════════════════════════════════════════════════════════════
        icon_section = ''
        if icon_players:
            cards = ''
            for p in icon_players[:4]:  # Limit to 4 icon players for landscape
                role  = p.role or ''
                color = rc(role)
                photo = tp_photo(p, 130)
                cards += (
                    '<div style="text-align:center;flex:0 0 180px;">'

                    # Outer gold glow ring — square with rounded corners
                    '<div style="width:150px;height:150px;border-radius:12px;margin:0 auto 10px;'
                    'background:linear-gradient(135deg,%(g)s,%(g2)s);padding:3px;'
                    'box-shadow:0 0 28px %(g)s77;">'
                    '<div style="width:100%%;height:100%%;border-radius:10px;overflow:hidden;'
                    'background:%(n)s;">%(photo)s</div>'
                    '</div>'

                    # Icon badge
                    '<div style="margin-top:-8px;margin-bottom:10px;position:relative;z-index:2;">'
                    '<span style="background:linear-gradient(135deg,%(g)s,%(g2)s);color:%(n)s;'
                    'font-size:8px;font-weight:900;letter-spacing:1px;padding:3px 12px;'
                    'border-radius:16px;text-transform:uppercase;'
                    'box-shadow:0 2px 8px rgba(232,160,32,0.45);">★ ICON</span>'
                    '</div>'

                    # Name
                    '<div style="color:%(nm_c)s;font-size:13px;font-weight:bold;'
                    'text-transform:uppercase;letter-spacing:0.5px;line-height:1.2;'
                    'padding:0 4px;">%(name)s</div>'

                    # Role badge
                    '<div style="margin-top:6px;">'
                    '<span style="background:%(c)s22;border:1px solid %(c)s99;'
                    'color:%(c)s;font-size:8px;font-weight:bold;padding:3px 10px;'
                    'border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">'
                    '%(role)s</span>'
                    '</div>'

                    '</div>'
                ) % {'g': GOLD, 'g2': GOLD2, 'n': NAVY3, 'nm_c': NAVY,
                     'c': color, 'photo': photo,
                     'name': p.name or '', 'role': role or '—'}

            icon_section = (
                '<div style="flex:0 0 auto;background:%(bg)s;padding:20px 32px;'
                'border-bottom:1px solid rgba(14,27,62,0.12);'
                'display:flex;align-items:flex-start;gap:16px;justify-content:center;'
                'overflow-x:auto;">'
                '%(cards)s'
                '</div>'
            ) % {'bg': LIGHT, 'g': GOLD, 'cards': cards}

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 4 — The Squad (all players, wrapping grid)
        # ══════════════════════════════════════════════════════════════════════
        squad_section = ''
        if regular_players:
            players_to_show = regular_players  # show all players
            
            def _render_compact_card(name, role, photo_b64, clr):
                if photo_b64:
                    photo_section = (
                        '<div style="width:100%;height:160px;background:{bg};display:flex;'
                        'align-items:center;justify-content:center;">'
                        '<img src="{src}" style="max-width:100%;max-height:160px;'
                        'object-fit:contain;display:block;">'
                        '</div>'
                    ).format(src=photo_b64, bg=LIGHT)
                else:
                    initials = ''.join(w[0] for w in (name or 'P').split()[:2]).upper()
                    photo_section = (
                        '<div style="width:100%;height:160px;background:{bg};'
                        'display:flex;align-items:center;justify-content:center;'
                        'font-size:36px;font-weight:900;color:{c};">{i}</div>'
                    ).format(bg=NAVY, c=clr, i=initials)
                return (
                    '<div style="width:calc(20% - 10px);border-radius:10px;overflow:hidden;'
                    'box-shadow:0 3px 10px rgba(15,36,71,0.15);border:2px solid {c}55;">'
                    '<div style="height:3px;background:{c};"></div>'
                    '{photo}'
                    '<div style="background:#fff;padding:6px 6px 7px;text-align:center;">'
                    '<div style="font-size:9px;font-weight:bold;color:#0d1b3e;'
                    'text-transform:uppercase;letter-spacing:0.4px;'
                    'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{nm}</div>'
                    '<span style="display:inline-block;margin-top:3px;background:{c}18;'
                    'border:1px solid {c}88;color:{c};font-size:7px;font-weight:bold;'
                    'padding:2px 7px;border-radius:8px;text-transform:uppercase;">'
                    '{role}</span>'
                    '</div>'
                    '</div>'
                ).format(c=clr, photo=photo_section, nm=name, role=role or '—')
            
            cards_html = ''.join(
                _render_compact_card(
                    p.player_id.name or '',
                    p.player_id.role or '',
                    b64uri(p.player_id.photo),
                    rc(p.player_id.role or '')
                ) for p in players_to_show
            )

            squad_section = (
                '<div style="flex:1;background:%(bg)s;padding:16px 20px;">'

                '<div style="font-size:10px;font-weight:bold;letter-spacing:5px;'
                'color:%(n)s;text-transform:uppercase;margin-bottom:12px;">'
                '★ THE SQUAD (%(cnt)d players)</div>'

                '<div style="display:flex;flex-wrap:wrap;gap:10px;">'
                '%(cards)s'
                '</div>'

                '</div>'
            ) % {'bg': LIGHT, 'n': NAVY, 'cnt': len(players_to_show), 'cards': cards_html}

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 5 — Footer (minimal, bottom of right panel)
        # ══════════════════════════════════════════════════════════════════════
        footer = (
            '<div style="flex:0 0 auto;height:40px;background:%(d)s;'
            'border-top:2px solid %(g)s;'
            'display:flex;align-items:center;justify-content:center;gap:10px;">'
            '<span style="color:rgba(255,255,255,0.4);font-size:9px;font-weight:bold;'
            'letter-spacing:3px;text-transform:uppercase;">POWERED BY</span>'
            '<span style="color:%(g)s;font-size:14px;font-weight:900;letter-spacing:2px;">'
            'AuctionChamp</span>'
            '</div>'
        ) % {'g': GOLD, 'd': DARK}

        # Close the right container
        right_container_end = '</div>'

        # ── JavaScript (no f-string — curly braces conflict) ─────────────────
        team_name_js = json.dumps(team.name or 'squad')
        js = (
            '<script>\n'
            '(function() {\n'
            '  var status = document.getElementById("poster-status");\n'
            '  var poster = document.getElementById("poster");\n'
            '  var name   = ' + team_name_js + ';\n'
            '  var imgs   = Array.from(poster.querySelectorAll("img"));\n'
            '  var loads  = imgs.map(function(img) {\n'
            '    return new Promise(function(res) {\n'
            '      if (img.complete && img.naturalWidth) { res(); return; }\n'
            '      img.onload = img.onerror = res;\n'
            '    });\n'
            '  });\n'
            '  status.textContent = "\\u231B Loading images\\u2026";\n'
            '  Promise.all(loads).then(function() {\n'
            '    status.textContent = "\\u231B Rendering poster\\u2026";\n'
            '    return html2canvas(poster, {\n'
            '      scale: 3, useCORS: true, allowTaint: true,\n'
            '      backgroundColor: "' + LIGHT + '",\n'
            '      logging: false, imageTimeout: 0,\n'
            '      width: poster.scrollWidth,\n'
            '      windowWidth: poster.scrollWidth + 40,\n'
            '      windowHeight: 1080\n'
            '    });\n'
            '  }).then(function(canvas) {\n'
            '    canvas.toBlob(function(blob) {\n'
            '      var url  = URL.createObjectURL(blob);\n'
            '      var link = document.createElement("a");\n'
            '      link.href     = url;\n'
            '      link.download = "squad-poster-" + name.replace(/\\s+/g,"-").toLowerCase() + ".jpg";\n'
            '      document.body.appendChild(link);\n'
            '      link.click();\n'
            '      document.body.removeChild(link);\n'
            '      setTimeout(function() { URL.revokeObjectURL(url); }, 2000);\n'
            '      status.style.background = "#065f46";\n'
            '      status.innerHTML = "\\u2713 Download started! You may close this tab.";\n'
            '    }, "image/jpeg", 0.96);\n'
            '  }).catch(function(err) {\n'
            '    console.error("Squad poster:", err);\n'
            '    status.style.background = "#7f1d1d";\n'
            '    status.textContent = "\\u26A0 Error: " + err.message;\n'
            '  });\n'
            '})();\n'
            '</script>'
        )

        # ── Assemble full HTML page ───────────────────────────────────────────
        html = (
            '<!DOCTYPE html><html lang="en"><head>'
            '<meta charset="UTF-8">'
            '<title>Squad Poster \u2014 ' + (team.name or 'Team') + '</title>'
            '<style>'
            '* { margin:0; padding:0; box-sizing:border-box; }'
            'body { background:#b8c8e0; font-family:Arial,Helvetica,sans-serif; padding-top:54px; }'
            '#poster-status {'
            '  position:fixed; top:0; left:0; right:0; z-index:9999;'
            '  background:#1e293b; color:#fff; padding:14px;'
            '  text-align:center; font-size:14px; font-family:Arial,sans-serif;'
            '}'
            '#poster {'
            '  width:1920px; min-height:1080px; height:auto; margin:20px auto 40px;'
            '  background:' + LIGHT + ';'
            '  box-shadow:0 16px 60px rgba(0,0,0,0.40);'
            '  overflow:visible; border-radius:4px;'
            '  display:flex; flex-direction:row; align-items:stretch;'
            '}'
            '</style>'
            '</head><body>'
            '<div id="poster-status">&#9203; Preparing\u2026</div>'
            '<div id="poster">'
            + tourn_section + right_container_start + team_section + icon_section + squad_section + footer + right_container_end +
            '</div>'
            '<script src="/auction_module/static/src/lib/html2canvas.min.js"></script>'
            + js +
            '</body></html>'
        )

        return request.make_response(
            html,
            headers=[
                ('Content-Type', 'text/html; charset=utf-8'),
                ('Cache-Control', 'no-store'),
            ]
        )

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
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )

            # Return 404 if tournament not found
            if not tournament:
                return self._not_found()

            theme = tournament.player_display_template or 'vanilla'

            # ── Football lookups (only needed for football tournaments) ─────────
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

            # ── Compute live slot availability ──────────────────────────────────
            max_reg = tournament.max_registrations
            current_count = 0
            slots_left = None  # None = unlimited
            if max_reg > 0:
                current_count = request.env['auction.team.player'].sudo().search_count([
                    ('tournament_id', '=', tournament.id),
                    ('state', '=', 'draft'),
                ])
                slots_left = max(0, max_reg - current_count)

            is_full = (max_reg > 0 and current_count >= max_reg)

            # ── Gate: closed by admin OR limit reached ──────────────────────────
            if not tournament.registration_open or is_full:
                # Sync the flag if the limit was hit but the flag wasn't updated yet
                if is_full and tournament.registration_open:
                    try:
                        tournament.sudo().write({'registration_open': False})
                    except Exception:
                        _logger.warning('player_register: could not auto-close registration for tournament %s', tournament.id, exc_info=True)
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
                }, lazy=False)
                return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

            tiers = request.env['auction.player.tier'].sudo().search(
                [('is_an_icon_tier', '=', False), ('tournament_id', '=', tournament.id)],
                order='name asc'
            )

            # ── POST: create player ─────────────────────────────────────────────
            if request.httprequest.method == 'POST':
                try:
                    vals = _build_player_vals_from_post(request, tournament)
                    player = request.env['auction.team.player'].sudo().create(vals)
                    # PRG: redirect to GET so that page refreshes don't re-submit the form
                    from urllib.parse import urlencode
                    qs = urlencode({'success': '1', 'player_id': player.id})
                    return werkzeug.utils.redirect(
                        '/{}/{}/player/register?{}'.format(db_name, tournament_slug, qs), 303
                    )
                except Exception as e:
                    ctx = {
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
                        'error': str(e),
                    }
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

            # ── GET: show form (or success view when redirected back after POST) ─
            success = kw.get('success') == '1'
            try:
                player_id_str = kw.get('player_id', '')
                player_id = int(player_id_str) if player_id_str else None
            except (ValueError, TypeError):
                player_id = None

            ctx = {
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
                'success': success,
                'player_id': player_id,
            }

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
                'expose_player_contact': bool(post.get('expose_player_contact')),
            }

            # Date
            date_str = _str('tournament_date')
            if date_str:
                from odoo.fields import Date
                try:
                    vals['tournament_date'] = Date.to_date(date_str)
                except Exception:
                    pass

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


def _football_display_payload(player):
    """Return JSON-serializable football attributes for a player, for JS displays.

    Always returns the keys so the projector/display JS can branch on
    ``tournament_type`` without KeyErrors. Empty when not a football player.
    """
    is_football = bool(player.tournament_id and player.tournament_id.tournament_type == 'football')
    empty_other = []
    if not is_football:
        return {
            'tournament_type': player.tournament_id.tournament_type if player.tournament_id else 'cricket',
            'dominant_position': '',
            'dominant_position_code': '',
            'secondary_positions': [],
            'preferred_foot': '',
            'age': '',
            'height': '',
            'weight': '',
            'work_rate': '',
            'p_category': '',
            'blood_group': '',
            'mobile': '',
            'location': '',
            'playing_styles': [],
            'strengths': [],
            'other_attributes': empty_other,
            'use_other_attributes': False,
        }
    foot_map = {'left': 'Left', 'right': 'Right', 'both': 'Both'}
    rate_map = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
    other_attributes = [
        {'label': a.label or '', 'value': a.value or ''}
        for a in player.other_attribute_ids
        if a.label and (a.value or '').strip()
    ]
    use_other = bool(other_attributes)
    return {
        'tournament_type': 'football',
        'dominant_position': player.dominant_position_id.name if player.dominant_position_id else '',
        'dominant_position_code': player.dominant_position_id.code if player.dominant_position_id else '',
        'secondary_positions': [] if use_other else [p.code or p.name for p in player.secondary_position_ids],
        'preferred_foot': foot_map.get(player.preferred_foot, ''),
        'age': '' if use_other else (player.age or ''),
        'height': player.height or '',
        'weight': player.weight or '',
        'work_rate': '' if use_other else rate_map.get(player.work_rate, ''),
        'p_category': player.p_category or '',
        'blood_group': player.blood_group or '',
        'mobile': player.masked_contact or '',
        'location': player.address or '',
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

    is_football = bool(tournament and tournament.tournament_type == 'football')

    vals = {
        'sl_no':         sl_no,
        'name':          name,
        'contact':       (post.get('contact') or '').strip(),
        'address':       (post.get('address') or '').strip(),
        'blood_group':   (post.get('blood_group') or '').strip(),
        'current_team':  (post.get('current_team') or '').strip(),
        'state':         'draft',
        'photo':         photo_data,
        'payment_proof': payment_proof_data,
    }

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

    return vals
