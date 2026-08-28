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
from datetime import date

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
