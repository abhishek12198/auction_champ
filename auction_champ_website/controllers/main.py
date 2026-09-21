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
import logging
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode
from dateutil.relativedelta import relativedelta

from odoo import http, fields
from odoo.http import request
from odoo.addons.website.controllers.main import Website
from odoo.addons.web.controllers.main import ensure_db
from odoo.addons.auction_login_theme.controllers.main import (
    AuctionLoginController,
    _safe_post_login_redirect,
    _session_user_is_logged_in,
)

_logger = logging.getLogger(__name__)


class AuctionChampHomepage(Website):
    """Override the website root to serve the AuctionChamp marketing page."""

    def _get_public_pricing_plans(self):
        """Build website pricing cards from SaaS plans."""
        config = request.env['auction.website.config'].sudo().get_singleton()
        contact_email = (config.contact_email or '').strip() or 'support@auctionchamp.in'
        plan_labels = {
            'standard': 'Starter',
            'classic': 'Classic',
            'pro': 'Pro',
            'pro_plus': 'Champion',
        }
        theme_labels = {
            'lemon': 'Lemon',
            'vanilla': 'Vanilla',
            'butterscotch': 'Butterscotch',
            'strawberry': 'Strawberry',
            'cherry': 'Cherry',
            'pistah': 'Pistah',
            'blueberry': 'Blueberry',
            'blackberry': 'Blueberry',
        }
        plans = request.env['ac.saas.plan'].sudo().search(
            [('active', '=', True)],
            order='sequence asc, id asc',
        )
        cards = []
        for plan in plans:
            themes = plan.get_allowed_templates() or []
            features = [
                'Up to %s tournaments' % (plan.max_tournaments or 0),
                'Up to %s teams per tournament' % (plan.max_teams_per_tournament or 0),
                'Up to %s players per tournament' % (plan.max_players_per_tournament or 0),
                'Random mode: %s' % ('Yes' if plan.allow_random_mode else 'No'),
                'Parallel tournaments (multi-device): %s' % (
                    'Yes' if plan.allow_parallel_sessions else 'No'
                ),
                'Themes: %s' % (
                    ', '.join(theme_labels.get(t, t.title()) for t in themes) if themes else '—'
                ),
            ]
            price_info = plan.get_website_price_display()
            cards.append({
                'name': '%s Plan' % plan_labels.get(plan.code, (plan.name or 'Plan')),
                'subtitle': plan.description or '',
                'badge': 'Recommended' if plan.recommended else '',
                'price_amount': price_info.get('amount') or '',
                'price_per_tournament': price_info.get('per_tournament') or '',
                'price_validity': price_info.get('validity') or '',
                'features': features,
                'plan_id': plan.id,
                'contact_url': 'mailto:%s?subject=%s%%20Plan%%20Enquiry' % (
                    contact_email,
                    (plan.name or 'AuctionChamp').replace(' ', '%20')
                ),
                'cta_label': 'Contact Us',
                'cta_buy': False,
                'is_highlighted': bool(plan.recommended),
            })
        return cards

    def _get_live_tournaments_data(self):
        """Return summarized data for all currently live tournaments (live_board_active=True).

        Each entry contains tournament info, the current player on stage,
        the latest auction history entry, and aggregate stats.  Used both
        for the initial server-render and by the polling JSON endpoint.
        """
        env = request.env
        db_name = env.cr.dbname

        live_tournaments = env['auction.tournament'].sudo().search([
            ('live_board_active', '=', True),
            ('active', '=', True),
        ])
        if not live_tournaments:
            return []

        def pub_img(model, record_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

        result = []
        for tournament in live_tournaments:
            # Stamp-first: respect the sold/unsold stamp window
            now_dt = fields.Datetime.now()
            on_stage = None
            if (tournament.stamp_expires_at
                    and tournament.stamp_expires_at > now_dt
                    and tournament.stamp_player_id):
                on_stage = tournament.stamp_player_id
            else:
                found = env['auction.team.player'].sudo().search([
                    ('is_on_stage', '=', True),
                    ('tournament_id', '=', tournament.id),
                ], limit=1)
                on_stage = found or None

            # Latest auction history entry for this tournament
            latest_bid = env['auction.history'].sudo().search([
                ('tournament_id', '=', tournament.id),
            ], order='id desc', limit=1)

            # Auction / team stats
            auctions = env['auction.auction'].sudo().search([
                ('tournament_id', '=', tournament.id),
            ])
            teams_count = len(auctions)
            players_sold = sum(len(a.player_ids) for a in auctions)
            players_in_auction = env['auction.team.player'].sudo().search_count([
                ('tournament_id', '=', tournament.id),
                ('state', '=', 'auction'),
            ])

            # Current player detail
            current_player_data = None
            if on_stage:
                base_price = 0
                for auc in auctions:
                    base = auc.base_point or 0
                    if on_stage.tier_id and auc.tier_limit_ids:
                        tl = auc.tier_limit_ids.filtered(
                            lambda l, tid=on_stage.tier_id.id: l.tier_id.id == tid
                        )
                        if tl and tl[0].base_point > 0:
                            base = tl[0].base_point
                    if base > base_price:
                        base_price = base

                sold_team_name = ''
                sold_team_logo = ''
                sold_points = 0
                if on_stage.state == 'sold' and on_stage.assigned_team_id:
                    auc_line = env['auction.auction.player'].sudo().search(
                        [('player_id', '=', on_stage.id)], limit=1
                    )
                    team = on_stage.assigned_team_id
                    sold_team_name = team.name or ''
                    sold_team_logo = pub_img('auction.team', team.id, 'logo') if team.logo else ''
                    sold_points = auc_line.points if auc_line else 0

                current_player_data = {
                    'name': on_stage.name or '',
                    'role': on_stage.role or '',
                    'photo_url': pub_img('auction.team.player', on_stage.id, 'photo') if on_stage.photo else '',
                    'tier_name': on_stage.tier_id.name if on_stage.tier_id else '',
                    'tier_color': on_stage.tier_color or '#2252b5',
                    'state': on_stage.state,
                    'sl_no': on_stage.sl_no or 0,
                    'base_price': base_price,
                    'sold_team_name': sold_team_name,
                    'sold_team_logo': sold_team_logo,
                    'sold_points': sold_points,
                }

            # Latest bid/history info
            current_bid_data = None
            if latest_bid:
                current_bid_data = {
                    'message': latest_bid.message or '',
                    'team_name': latest_bid.team_id.name if latest_bid.team_id else '',
                    'team_logo_url': (
                        pub_img('auction.team', latest_bid.team_id.id, 'logo')
                        if latest_bid.team_id and latest_bid.team_id.logo else ''
                    ),
                }

            result.append({
                'tournament_id': tournament.id,
                'tournament_slug': tournament.slug or '',
                'name': tournament.name or '',
                'description': tournament.description or '',
                'logo_url': pub_img('auction.tournament', tournament.id, 'logo') if tournament.logo else '',
                'live_board_url': '/{}/{}/auction/live-board'.format(db_name, tournament.slug)
                                  if tournament.slug else '/auction/live-board',
                'is_break': tournament.break_time_active,
                'current_player': current_player_data,
                'current_bid': current_bid_data,
                'teams_count': teams_count,
                'players_sold': players_sold,
                'players_in_auction': players_in_auction,
            })

        return result

    def _calendar_public_domain(self):
        """Tournaments with Show on Website Calendar, including archived.

        Naming ``active`` in the domain stops Odoo from injecting
        ``active=True`` if ``active_test=False`` is lost on the public env.
        """
        return [
            ('website_calendar_visible', '=', True),
            '|',
            ('active', '=', True),
            ('active', '=', False),
        ]

    def _calendar_tournament_env(self):
        return request.env['auction.tournament'].sudo().with_context(
            active_test=False,
            auction_skip_tournament_security=True,
        )

    def _parse_calendar_month(self, month_str, today):
        try:
            year, month = [int(p) for p in (month_str or '').split('-')[:2]]
            if 1 <= month <= 12 and 2000 <= year <= 2100:
                return year, month
        except (TypeError, ValueError):
            pass
        return today.year, today.month

    def _calendar_event_card(self, tournament, db_name, type_labels):
        def pub_img(model, record_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

        date_display = ''
        if hasattr(tournament, 'format_tournament_dates'):
            date_display = tournament.format_tournament_dates()
        if not date_display and tournament.tournament_date_display:
            date_display = tournament.tournament_date_display
        completed = self._calendar_tournament_is_completed(tournament)
        return {
            'id': tournament.id,
            'name': tournament.name or '',
            'sport': type_labels.get(tournament.tournament_type, tournament.tournament_type or ''),
            'date_display': date_display or 'Dates to be announced',
            'venue': tournament.get_venue_label() or 'Venue to be announced',
            'logo_url': (
                pub_img('auction.tournament', tournament.id, 'logo')
                if tournament.logo else ''
            ),
            'is_live': bool(tournament.live_board_active),
            'is_archived': not bool(tournament.active),
            'is_completed': completed,
            'live_url': (
                '/{}/{}/auction/live-board'.format(db_name, tournament.slug)
                if tournament.live_board_active and tournament.slug else ''
            ),
            'register_url': (
                tournament.registration_url
                if tournament.registration_open and tournament.registration_url
                else ''
            ),
            'squad_url': (
                '/calendar/squad/%s' % tournament.id
                if self._calendar_squads_visible(tournament) else ''
            ),
        }

    def _calendar_tournament_is_completed(self, tournament):
        """Badge only: archived, declared complete, or last tournament day passed."""
        if not tournament.active:
            return True
        if self._calendar_auction_is_complete(tournament):
            return True
        dates = self._tournament_calendar_dates(tournament)
        today = fields.Date.context_today(tournament)
        return bool(dates and dates[-1] < today)

    def _calendar_auction_is_complete(self, tournament):
        """True when the auction itself is finished. Archive status is ignored."""
        if not tournament:
            return False
        if getattr(tournament, 'auction_declared_complete', False):
            return True
        Player = request.env['auction.team.player'].sudo().with_context(
            active_test=False,
        )
        domain = [
            ('tournament_id', '=', tournament.id),
            ('icon_player', '=', False),
        ]
        leftover = Player.search_count(
            domain + [('state', 'in', ('draft', 'auction', 'unsold'))]
        )
        if leftover:
            return False
        return bool(Player.search_count(domain + [('state', '=', 'sold')]))

    def _calendar_squads_visible(self, tournament):
        """View Squads after the auction is finished, for the last 3 months.

        Archived and live (non-archived) tournaments both qualify. Calendar
        dates only gate the 3-month window, not whether the auction is done.
        """
        if not self._calendar_auction_is_complete(tournament):
            return False
        dates = self._tournament_calendar_dates(tournament)
        if not dates:
            return False
        today = fields.Date.context_today(tournament)
        cutoff = today - relativedelta(months=3)
        return dates[-1] >= cutoff

    def _calendar_tournament_visible(self, tournament):
        if not tournament or not tournament.exists():
            return False
        return bool(tournament.website_calendar_visible)

    def _get_public_squad_data(self, tournament):
        env = request.env
        db_name = env.cr.dbname
        # Completed/archived tournaments deactivate teams and players.
        Team = env['auction.team'].sudo().with_context(active_test=False)
        Player = env['auction.team.player'].sudo().with_context(active_test=False)
        teams = Team.search(
            [('tournament_id', '=', tournament.id)],
            order='name asc',
        )
        # Every player still assigned to a team — not only sold/icon.
        players = Player.search([
            ('tournament_id', '=', tournament.id),
            ('assigned_team_id', '!=', False),
        ], order='icon_player desc, sl_no asc, name asc')
        by_team = {}
        extra_teams = Team.browse()
        for player in players:
            team = player.assigned_team_id
            team_id = team.id
            if not team_id:
                continue
            by_team.setdefault(team_id, []).append(player)
            if team_id not in teams.ids:
                extra_teams |= team
        if extra_teams:
            teams |= extra_teams

        def pub_img(model, record_id, field, sz=''):
            url = '/%s/auction/public/image/%s/%d/%s' % (
                db_name, model, record_id, field,
            )
            qs = ['v=3']
            if sz:
                qs.insert(0, 'sz=%s' % sz)
            return '%s?%s' % (url, '&'.join(qs))

        blocks = []
        for team in teams.sorted(lambda t: (t.name or '').lower()):
            owner_name = (team.manager or '').strip()
            team_players = []
            for player in by_team.get(team.id, []):
                team_players.append({
                    'id': player.id,
                    'name': (player.name or '').upper(),
                    'photo_url': pub_img('auction.team.player', player.id, 'photo'),
                    'is_icon': bool(player.icon_player),
                })
            blocks.append({
                'id': team.id,
                'name': team.name or 'Team',
                'logo_url': pub_img('auction.team', team.id, 'logo'),
                'owner_name': owner_name,
                'owner_photo_url': (
                    pub_img('auction.team', team.id, 'owner_photo')
                    if owner_name else ''
                ),
                'players': team_players,
            })
        return blocks

    def _tournament_calendar_dates(self, tournament):
        DateLine = request.env['auction.tournament.date'].sudo().with_context(
            active_test=False,
            auction_skip_tournament_security=True,
        )
        dates = sorted(
            d for d in DateLine.search([('tournament_id', '=', tournament.id)]).mapped('date')
            if d
        )
        if not dates and hasattr(tournament, '_parse_tournament_dates_char'):
            dates = tournament._parse_tournament_dates_char() or []
        if not dates and tournament.tournament_date:
            dates = [tournament.tournament_date]
        return dates

    def _calendar_query(self, month=None, district_id=None, extra=None):
        params = {}
        if month:
            params['month'] = month
        if district_id:
            params['district'] = district_id
        elif district_id == 0:
            params['district'] = 'all'
        if extra:
            params.update(extra)
        qs = urlencode(params)
        return '/calendar?%s' % qs if qs else '/calendar'

    def _calendar_client_ip(self):
        req = request.httprequest
        forwarded = (req.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        return forwarded or (req.remote_addr or '')

    def _calendar_ip_is_private(self, ip):
        if not ip:
            return True
        if ip in ('127.0.0.1', '::1', 'localhost'):
            return True
        if ip.startswith('10.') or ip.startswith('192.168.') or ip.startswith('127.'):
            return True
        if ip.startswith('172.'):
            try:
                second = int(ip.split('.')[1])
            except (IndexError, ValueError):
                return False
            return 16 <= second <= 31
        return False

    def _calendar_fetch_json(self, url, timeout=2.5, headers=None):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw or '{}')
        except Exception:
            _logger.debug('calendar geo lookup failed for %s', url, exc_info=True)
            return {}

    def _calendar_geo_names_from_ip(self, ip):
        if self._calendar_ip_is_private(ip):
            return []
        data = self._calendar_fetch_json(
            'http://ip-api.com/json/%s?fields=status,city,district,regionName,country' % ip,
        )
        if data.get('status') == 'success':
            return [
                data.get('district') or '',
                data.get('city') or '',
                data.get('regionName') or '',
                data.get('country') or '',
            ]
        data = self._calendar_fetch_json('https://ipwho.is/%s' % ip)
        if data.get('success'):
            return [
                ((data.get('city') or '')),
                ((data.get('region') or '')),
                ((data.get('country') or '')),
            ]
        return []

    def _calendar_geo_names_from_latlng(self, lat, lng):
        url = (
            'https://nominatim.openstreetmap.org/reverse?lat=%s&lon=%s'
            '&format=json&addressdetails=1' % (lat, lng)
        )
        data = self._calendar_fetch_json(url, headers={
            'User-Agent': 'AuctionChampCalendar/1.0',
            'Accept': 'application/json',
        })
        addr = data.get('address') or {}
        return [
            addr.get('city') or '',
            addr.get('town') or '',
            addr.get('village') or '',
            addr.get('municipality') or '',
            addr.get('county') or '',
            addr.get('state_district') or '',
            addr.get('district') or '',
            addr.get('state') or '',
            addr.get('country') or '',
        ]

    def _calendar_match_district(self, names):
        Location = request.env['auction.location'].sudo()
        return Location.match_geo_to_district(names)

    def _calendar_district_from_ip(self):
        return self._calendar_match_district(
            self._calendar_geo_names_from_ip(self._calendar_client_ip())
        )

    def _calendar_district_choices(self, selected_id):
        Location = request.env['auction.location'].sudo()
        rows = []
        for loc in Location.calendar_districts():
            rows.append({
                'id': loc.id,
                'name': loc.name or loc.complete_name or ('Location #%s' % loc.id),
                'selected': bool(selected_id and loc.id == selected_id),
            })
        return rows

    def _get_calendar_month_data(self, month=None, district_id=None):
        """Month grid: each tournament date is a cell, not a stacked card list."""
        env = request.env
        db_name = env.cr.dbname
        today = fields.Date.context_today(env['auction.tournament'])
        year, month_n = self._parse_calendar_month(month, today)
        first = date(year, month_n, 1)
        if month_n == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month_n + 1, 1)
        prev = first - timedelta(days=1)
        prev_key = prev.strftime('%Y-%m')
        next_key = nxt.strftime('%Y-%m')

        start = first - timedelta(days=first.weekday())  # Monday
        type_labels = dict(
            env['auction.tournament']._fields['tournament_type'].selection or []
        )
        tournaments = self._calendar_tournament_env().search(
            self._calendar_public_domain(),
            order='tournament_date asc, name asc',
        )
        if district_id:
            district = env['auction.location'].sudo().browse(int(district_id)).exists()
            if district:
                loc_ids = district.calendar_location_ids()
                tournaments = tournaments.filtered(
                    lambda t: t.venue and t.venue.id in loc_ids
                )

        by_day = defaultdict(list)
        tbd = []
        seen_tbd = set()
        for tournament in tournaments:
            card = self._calendar_event_card(tournament, db_name, type_labels)
            dates = self._tournament_calendar_dates(tournament)
            if not dates:
                if tournament.id not in seen_tbd:
                    seen_tbd.add(tournament.id)
                    tbd.append(card)
                continue
            for day in dates:
                by_day[fields.Date.to_string(day)].append(card)

        weeks = []
        cur = start
        for _week in range(6):
            week = []
            for _dow in range(7):
                iso = fields.Date.to_string(cur)
                events = by_day.get(iso, [])
                week.append({
                    'iso': iso,
                    'num': cur.day,
                    'label': cur.strftime('%d %B %Y'),
                    'in_month': cur.month == month_n,
                    'is_today': cur == today,
                    'events': events,
                    'extra': max(0, len(events) - 2),
                    'preview': events[:2],
                })
                cur += timedelta(days=1)
            weeks.append(week)

        selected_iso = fields.Date.to_string(today) if today.year == year and today.month == month_n else ''
        if not selected_iso:
            for week in weeks:
                for cell in week:
                    if cell['in_month'] and cell['events']:
                        selected_iso = cell['iso']
                        break
                if selected_iso:
                    break

        district_key = district_id or 0
        districts = self._calendar_district_choices(district_id)
        return {
            'month_label': first.strftime('%B %Y'),
            'prev_url': self._calendar_query(prev_key, district_key),
            'next_url': self._calendar_query(next_key, district_key),
            'today_url': self._calendar_query(today.strftime('%Y-%m'), district_key),
            'weeks': weeks,
            'selected_iso': selected_iso,
            'tbd': tbd,
            'month_event_count': sum(
                1 for days in by_day
                if days.startswith('%04d-%02d' % (year, month_n))
            ),
            'district_id': district_id or False,
            'districts': districts,
            'district_label': next(
                (row['name'] for row in districts if row.get('selected')),
                'All districts',
            ),
        }

    @http.route('/', type='http', auth='public', website=True, sitemap=True)
    def index(self, **kw):
        try:
            Config = request.env['auction.website.config'].sudo()
            config = Config.get_singleton()
            hero_stats = Config.get_hero_stats()
            faq_items = request.env['auction.website.faq'].sudo().search(
                [('active', '=', True)], order='sequence asc'
            )
            pricing_plans = self._get_public_pricing_plans()
            live_tournaments = self._get_live_tournaments_data()
            return request.render('auction_champ_website.homepage', {
                'config': config,
                'hero_stats': hero_stats,
                'faq_items': faq_items,
                'pricing_plans': pricing_plans,
                'current_year': date.today().year,
                'live_tournaments': live_tournaments,
            })
        except Exception:
            _logger.exception("AuctionChamp homepage render error — falling back to default")
            return super().index(**kw)

    @http.route('/privacy-policy', type='http', auth='public', website=True, sitemap=True)
    def privacy_policy(self, **kw):
        """Render public privacy policy page for website visitors."""
        return request.render('auction_champ_website.privacy_policy_page', {
            'current_year': date.today().year,
        })

    @http.route('/terms-and-conditions', type='http', auth='public', website=True, sitemap=True)
    def terms_and_conditions(self, **kw):
        """Render public terms and conditions page for website visitors."""
        return request.render('auction_champ_website.terms_conditions_page', {
            'current_year': date.today().year,
        })

    @http.route('/user-manual', type='http', auth='public', website=True, sitemap=True)
    def user_manual(self, **kw):
        """Render public AuctionChamp user manual page."""
        return request.render('auction_champ_website.user_manual_page', {
            'current_year': date.today().year,
        })

    @http.route(
        '/calendar/squad/<int:tournament_id>',
        type='http', auth='public', website=True, sitemap=False,
    )
    def calendar_squad(self, tournament_id, **kw):
        """Public squad board for a completed tournament."""
        tournament = self._calendar_tournament_env().browse(tournament_id)
        if (
            not self._calendar_tournament_visible(tournament)
            or not self._calendar_squads_visible(tournament)
        ):
            return request.not_found()
        type_labels = dict(
            tournament._fields['tournament_type'].selection or []
        )
        return request.render('auction_champ_website.calendar_squad_page', {
            'current_year': date.today().year,
            'tournament_name': tournament.name or 'Tournament',
            'sport': type_labels.get(tournament.tournament_type, ''),
            'date_display': (
                tournament.format_tournament_dates()
                or tournament.tournament_date_display
                or ''
            ),
            'venue': tournament.get_venue_label(),
            'logo_url': (
                '/auction/public/image/auction.tournament/%d/logo' % tournament.id
                if tournament.logo else ''
            ),
            'teams': self._get_public_squad_data(tournament),
        })

    @http.route('/calendar', type='http', auth='public', website=True, sitemap=True)
    def calendar(self, month=None, district=None, **kw):
        """Public month-grid calendar: tournaments sit on their dates."""
        if district is None:
            geo = self._calendar_district_from_ip()
            if geo:
                return request.redirect(
                    self._calendar_query(month, geo.id, extra={'geo': 'ip'}),
                    code=302,
                )
        district_id = False
        if district and str(district).lower() not in ('all', '0', ''):
            try:
                district_id = int(district)
            except (TypeError, ValueError):
                district_id = False
        data = self._get_calendar_month_data(month=month, district_id=district_id)
        return request.render('auction_champ_website.calendar_page', {
            'current_year': date.today().year,
            'month_label': data['month_label'],
            'prev_url': data['prev_url'],
            'next_url': data['next_url'],
            'today_url': data['today_url'],
            'weeks': data['weeks'],
            'selected_iso': data['selected_iso'],
            'tbd': data['tbd'],
            'month_event_count': data['month_event_count'],
            'districts': data['districts'],
            'district_id': data['district_id'],
            'district_label': data['district_label'],
            'calendar_month': month or '',
        })

    @http.route('/calendar/locate', type='http', auth='public', website=True, csrf=False)
    def calendar_locate(self, lat=None, lng=None, **kw):
        """Match browser GPS coordinates to a City / Location district."""
        district_id = False
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            lat_f = lng_f = None
        if lat_f is not None and lng_f is not None:
            district = self._calendar_match_district(
                self._calendar_geo_names_from_latlng(lat_f, lng_f)
            )
            district_id = district.id if district else False
        return request.make_response(
            json.dumps({'district_id': district_id}),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-store'),
            ],
        )

    @http.route('/auction/live-tournaments/data', type='http', auth='public', website=True, csrf=False)
    def live_tournaments_data(self, **kw):
        """JSON endpoint returning summarized live tournament data for homepage auto-refresh."""
        try:
            data = self._get_live_tournaments_data()
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
            )
        except Exception:
            _logger.exception("Error fetching live tournaments data")
            return request.make_response(
                json.dumps([]),
                headers=[('Content-Type', 'application/json')]
            )


class AuctionChampWebsiteLogin(AuctionLoginController):
    """Website layer: logged-in visitors hitting /web/login go straight to /web."""

    @http.route('/web/login', type='http', auth='none', sitemap=False)
    def web_login(self, redirect=None, **kw):
        ensure_db()
        if request.httprequest.method == 'GET' and _session_user_is_logged_in():
            return request.redirect(_safe_post_login_redirect(redirect))
        return super().web_login(redirect=redirect, **kw)
