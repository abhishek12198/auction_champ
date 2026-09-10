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

from odoo import http, fields
from odoo.http import request
from odoo.addons.website.controllers.main import Website

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
            'blackberry': 'Blackberry',
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
        """Include archived tournaments; Odoo would otherwise hide active=False."""
        return [
            '|', '|', '|',
            ('website_calendar_visible', '=', True),
            ('live_board_active', '=', True),
            ('registration_open', '=', True),
            ('active', '=', False),
        ]

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
            'venue': (tournament.venue or '').strip() or 'Venue to be announced',
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
            'squad_url': '/calendar/squad/%s' % tournament.id if completed else '',
        }

    def _calendar_tournament_is_completed(self, tournament):
        """Archived, declared complete, or last tournament day already passed."""
        if not tournament.active:
            return True
        if getattr(tournament, 'auction_declared_complete', False):
            return True
        dates = self._tournament_calendar_dates(tournament)
        today = fields.Date.context_today(tournament)
        return bool(dates and dates[-1] < today)

    def _calendar_tournament_visible(self, tournament):
        if not tournament or not tournament.exists():
            return False
        return bool(
            tournament.website_calendar_visible
            or tournament.live_board_active
            or tournament.registration_open
            or not tournament.active
        )

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
        dates = sorted(d for d in tournament.tournament_date_ids.mapped('date') if d)
        if not dates and hasattr(tournament, '_parse_tournament_dates_char'):
            dates = tournament._parse_tournament_dates_char() or []
        if not dates and tournament.tournament_date:
            dates = [tournament.tournament_date]
        return dates

    def _get_calendar_month_data(self, month=None):
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
        tournaments = env['auction.tournament'].sudo().with_context(
            active_test=False,
        ).search(
            self._calendar_public_domain(),
            order='tournament_date asc, name asc',
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

        return {
            'month_label': first.strftime('%B %Y'),
            'prev_url': '/calendar?month=%s' % prev_key,
            'next_url': '/calendar?month=%s' % next_key,
            'today_url': '/calendar?month=%s' % today.strftime('%Y-%m'),
            'weeks': weeks,
            'selected_iso': selected_iso,
            'tbd': tbd,
            'month_event_count': sum(
                1 for days in by_day
                if days.startswith('%04d-%02d' % (year, month_n))
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
        tournament = request.env['auction.tournament'].sudo().with_context(
            active_test=False,
        ).browse(tournament_id)
        if (
            not self._calendar_tournament_visible(tournament)
            or not self._calendar_tournament_is_completed(tournament)
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
            'venue': (tournament.venue or '').strip(),
            'logo_url': (
                '/auction/public/image/auction.tournament/%d/logo' % tournament.id
                if tournament.logo else ''
            ),
            'teams': self._get_public_squad_data(tournament),
        })

    @http.route('/calendar', type='http', auth='public', website=True, sitemap=True)
    def calendar(self, month=None, **kw):
        """Public month-grid calendar: tournaments sit on their dates."""
        data = self._get_calendar_month_data(month=month)
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
        })

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
