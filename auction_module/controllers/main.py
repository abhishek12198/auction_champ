# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

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
            old_cr, old_uid, old_env = request._cr, request._uid, request._env
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
        }
        template_ref = template_map.get(theme, 'auction_module.player_template_new')
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
        }.get(theme, '#b71c1c')

        _unsold_text = '#090912' if theme == 'butterscotch' else '#fff'

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
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

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
            on_stage = request.env['auction.team.player'].sudo().search(
                [('is_on_stage', '=', True)], limit=1
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
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
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
                }
                chosen = tournament_id.player_display_template if tournament_id else 'vanilla'
                template_ref = template_map.get(chosen, 'auction_module.player_template_new')
                html = request.render(template_ref, {
                    'player': player,
                    'tournament': tournament_id,
                    'auction_ids': auction_ids,
                    'db_name': db_name,
                }, lazy=False)
            else:
                theme = tournament_id.player_display_template if tournament_id else 'vanilla'
                t_domain = [('tournament_id', '=', tournament_id.id)] if tournament_id else []
                sold_count = request.env['auction.team.player'].sudo().search_count(
                    t_domain + [('state', '=', 'sold'), ('icon_player', '=', False)]
                )
                if sold_count:
                    unsold_count = request.env['auction.team.player'].sudo().search_count(
                        t_domain + [('state', '=', 'unsold'), ('icon_player', '=', False)]
                    )
                    auction_ids = request.env['auction.auction'].sudo().search(
                        [('tournament_id', '=', tournament_id.id)] if tournament_id else []
                    )
                    html = request.render("auction_module.thank_you_template", {
                        'tournament': tournament_id,
                        'theme': theme,
                        'auction_ids': auction_ids,
                        'sold_count': sold_count,
                        'unsold_count': unsold_count,
                        'db_name': db_name,
                    }, lazy=False)
                else:
                    html = request.render("auction_module.welcome_message_template", {
                        'tournament': tournament_id,
                        'theme': theme,
                        'db_name': db_name,
                    }, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/auction/display_auction/remaining-players', type='http', auth='public', website=True, sitemap=False)
    def display_remaining_players(self, **kwargs):
        """Standalone page loaded inside the Remaining Players drawer iframe."""
        env = request.env
        tournament = self._resolve_tournament()
        t_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        players = env['auction.team.player'].sudo().search(
            t_domain + [('state', '=', 'auction'), ('icon_player', '=', False)],
            order='sl_no asc',
        )

        # Resolve theme: prefer explicit ?theme= param, then tournament setting
        theme = kwargs.get('theme', '') or (tournament.player_display_template if tournament else '') or 'vanilla'

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
        return request.render('auction_module.remaining_players_template', {
            'tier_groups':  tier_groups,
            'total_count':  len(players),
            'theme':        theme,
        })

    @http.route('/auction/get/players/team/<int:team_id>', type='http', auth='public', website=True)
    def get_team_players(self, team_id):
        player_data_list = []
        team_players = request.env['auction.auction.player'].search([('auction_id.team_id', '=', team_id)])

        team = request.env['auction.team'].browse(team_id)
        tournament = self._resolve_tournament()
        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        icon_players = request.env['auction.team.player'].get_icon_players(team_id)
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
        return request.render(template_ref, {
            'players': player_data_list,
            'team': team,
            'tournament': tournament,
            'theme': theme,
        })

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
                    '--quality', '100',
                    '--width', '50',  # Set the desired width
                    '--height', '500',  # Set the desired height
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

    @http.route(['/auction/projector', '/auction/projector/'],
                type='http', auth="none", website=False, sitemap=False)
    def projector_legacy(self, **kw):
        """Redirect legacy URL to db+slug prefixed URL."""
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            dbs = db_list(force=True, httprequest=request.httprequest)
            db_name = dbs[0] if dbs else None
        if not db_name:
            return self._not_found()
        slug = kw.get('t', '')
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
            html = request.render('auction_module.projector_template', {
                'tournament': tournament,
                'theme': theme,
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
            if player.photo:
                photo = player.photo.decode('utf-8') if isinstance(player.photo, bytes) else player.photo
            team_logo = ''
            team_name = ''
            if player.assigned_team_id and player.assigned_team_id.logo:
                lg = player.assigned_team_id.logo
                team_logo = lg.decode('utf-8') if isinstance(lg, bytes) else lg
                team_name = player.assigned_team_id.name
            sold_points = 0
            if player.state == 'sold':
                auction_line = request.env['auction.auction.player'].sudo().search(
                    [('player_id', '=', player.id)], limit=1)
                sold_points = auction_line.points if auction_line else 0
            return {
                'player': {
                    'id': player.id,
                    'sl_no': player.sl_no or '',
                    'name': player.name or '',
                    'role': player.role or '',
                    'batting_style': player.batting_style or '',
                    'bowling_style': player.bowling_style or '',
                    'photo': photo,
                    'tier_name': player.tier_id.name if player.tier_id else '',
                    'tier_color': player.tier_color or '#3498db',
                    'base_price': player.effective_base_price or player.base_price or 0,
                    'sold_points': sold_points,
                    'state': state_override or player.state,
                    'team_name': team_name,
                    'team_logo': team_logo,
                },
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
            ('Content-Type', 'image/png'),
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
            ('Content-Type', 'image/png'),
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
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
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
        from odoo.http import db_monodb, db_list
        db_name = db_monodb(request.httprequest)
        if not db_name:
            # If multiple DBs exist, pick the first one
            dbs = db_list(force=True, httprequest=request.httprequest)
            if dbs:
                db_name = dbs[0]
            else:
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
                }

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
            auctions = env['auction.auction'].sudo().search(
                [('tournament_id', '=', tournament.id)]
            )
            for auc in auctions:
                team = auc.team_id
                if team:
                    result['teams'].append({
                        'id': team.id,
                        'name': team.name or '',
                        'logo_url': pub_img('auction.team', team.id, 'logo') if team.logo else '',
                        'remaining_points': auc.remaining_points,
                        'manager': team.manager or '',
                        'players': [
                            {
                                'name': line.player_id.name or '',
                                'photo_url': pub_img('auction.team.player', line.player_id.id, 'photo')
                                             if line.player_id and line.player_id.photo else '',
                                'role': line.player_id.role or '',
                                'points': line.points,
                            }
                            for line in auc.player_ids if line.player_id
                        ],
                    })

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        )

    # ── Auction Dashboard ─────────────────────────────────────────────────────

    @http.route('/auction/dashboard', type='http', auth='user', website=True)
    def auction_dashboard(self, **kw):
        tournament = self._resolve_tournament()
        return request.render('auction_module.auction_dashboard_template', {
            'tournament': tournament,
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

        # ── State counts ──────────────────────────────────────────────────────
        states = ['draft', 'auction', 'sold', 'unsold']
        state_counts = {s: Player.search_count([('state', '=', s)]) for s in states}
        total = sum(state_counts.values())

        # ── Last 10 draft players ─────────────────────────────────────────────
        last_draft = Player.search([('state', '=', 'draft')], order='create_date desc', limit=10)
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
            count = Player.search_count([
                ('create_date', '>=', fields.Datetime.to_string(day_start_utc)),
                ('create_date', '<=', fields.Datetime.to_string(day_end_utc)),
            ])
            daily.append({'label': day.strftime('%d %b'), 'count': count})

        # ── Role distribution ─────────────────────────────────────────────────
        all_players = Player.search([])
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
        icon_count = Player.search_count([('icon_player', '=', True)])

        # ── Amount paid / unpaid ──────────────────────────────────────────────
        paid_count   = Player.search_count([('amount_paid', '=', True)])
        unpaid_count = Player.search_count([('amount_paid', '=', False)])

        # ── Players per team (sold players grouped by team) ───────────────────
        team_counts = {}
        for p in all_players:
            if p.assigned_team_id:
                tname = p.assigned_team_id.name or 'Unknown'
                team_counts[tname] = team_counts.get(tname, 0) + 1
        team_player_counts = [{'label': k, 'count': v}
                               for k, v in sorted(team_counts.items(), key=lambda x: -x[1])]

        # ── Icon / Key players with team assignment ───────────────────────────
        icon_players = Player.search([('icon_player', '=', True)], order='assigned_team_id, name')
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
                    tournament.sudo().write({'registration_open': False})
                tiers_all = request.env['auction.player.tier'].sudo().search([], order='name asc')
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
                }, lazy=False)
                return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

            tiers = request.env['auction.player.tier'].sudo().search([('is_an_icon_tier', '=', False)], order='name asc')
            ctx = {
                'tournament': tournament,
                'tiers': tiers,
                'theme': theme,
                'db_name': db_name,
                'tournament_slug': tournament_slug,
                'slots_left': slots_left,
                'max_registrations': max_reg,
                'current_count': current_count,
            }

            # ── POST: create player ─────────────────────────────────────────────
            if request.httprequest.method == 'POST':
                try:
                    vals = _build_player_vals_from_post(request, tournament)
                    player = request.env['auction.team.player'].sudo().create(vals)
                    ctx.update({'success': True, 'player_id': player.id})
                except Exception as e:
                    ctx.update({'error': str(e)})

            html = request.render('auction_module.player_registration_form', ctx, lazy=False)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

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

    @http.route('/<string:db_name>/player/card/<int:player_id>', type='http', auth='none', website=False, sitemap=False)
    def player_card_download(self, db_name, player_id, **kw):
        """Stream the themed player-card PDF for the given player (public, read-only)."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            player = request.env['auction.team.player'].sudo().browse(player_id)
            if not player.exists():
                return self._not_found()

            tournament = player.tournament_id
            theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'

            report_map = {
                'vanilla':      'auction_module.action_report_player_card',
                'butterscotch': 'auction_module.action_report_player_card_butterscotch',
                'strawberry':   'auction_module.action_report_player_card_strawberry',
                'cherry':       'auction_module.action_report_player_card_cherry',
                'pistah':       'auction_module.action_report_player_card_pistah',
            }
            report_ref = report_map.get(theme, 'auction_module.action_report_player_card')

            try:
                report = request.env.ref(report_ref).sudo()
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
        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ]
        )


def _build_player_vals_from_post(request, tournament):
    """Extract and validate POST form data into a dict for auction.team.player.create()."""
    post = request.httprequest.form
    files = request.httprequest.files

    name = (post.get('name') or '').strip()
    if not name:
        raise ValueError("Player name is required.")

    # Determine next sl_no
    last = request.env['auction.team.player'].sudo().search(
        [], limit=1, order='sl_no desc'
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

    vals = {
        'sl_no':         sl_no,
        'name':          name,
        'role':          post.get('role') or '',
        'batting_style': post.get('batting_style') or 'Right Handed',
        'bowling_style': post.get('bowling_style') or 'Right Arm',
        'contact':       (post.get('contact') or '').strip(),
        'address':       (post.get('address') or '').strip(),
        'blood_group':   (post.get('blood_group') or '').strip(),
        'current_team':  (post.get('current_team') or '').strip(),
        'state':         'draft',
        'photo':         photo_data,
        'payment_proof': payment_proof_data,
    }
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
