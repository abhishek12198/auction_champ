# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AuctionAuctioneerController(http.Controller):
    """
    Auctioneer Console routes + live-board data endpoint extension.

    NOTE: This is intentionally a *separate* http.Controller subclass (not
    inheriting from auction_module's Auction controller).  Subclassing the
    parent controller in Odoo causes the routing system to treat the child as
    a full replacement, silently dropping every parent route that the child
    does not explicitly re-declare.  The safe pattern for Odoo addons is to
    register the same URL path in a new controller class; the last-loaded
    module's handler wins.
    """

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_tournament():
        """Return the tournament scoped to the current logged-in user.

        Priority:
        1. The user's ``tournament_id`` field on their res.users profile.
        2. The single tournament flagged ``active = True`` (admin fallback).
        """
        try:
            user = request.env['res.users'].sudo().browse(request.uid)
            if user.tournament_id:
                return user.tournament_id
        except Exception:
            pass
        return request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )

    @staticmethod
    def _pub_img(model, record_id, field):
        return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

    @staticmethod
    def _get_effective_base(auction, player):
        """Return tier-specific base_point if configured, else global base_point."""
        if player and player.tier_id and auction.tier_limit_ids:
            tl = auction.tier_limit_ids.filtered(
                lambda l: l.tier_id.id == player.tier_id.id
            )
            if tl and tl[0].base_point > 0:
                return tl[0].base_point
        return auction.base_point

    @staticmethod
    def _next_bid(auction, current_bid, effective_base):
        """
        Return the next valid bid amount based on the auction's bid slabs.
        If no bid has been placed (current_bid == 0) the starting bid is the
        effective base price.
        """
        if current_bid == 0:
            return effective_base

        slabs = auction.auction_bid_slab_ids.sorted('from_amount', reverse=True)
        for slab in slabs:
            if current_bid >= slab.from_amount:
                return current_bid + slab.increment

        # Below all slab thresholds — increment by 1 as a safe fallback
        return current_bid + 1

    # ── Live-board data override ───────────────────────────────────────────
    # Same URL as auction_module's route; last-loaded module wins, so this
    # handler runs instead and injects current_bid / current_bid_team into the
    # payload before returning it to the live board JS.

    @http.route(
        '/<string:db_name>/<string:tournament_slug>/auction/live-board/data',
        type='http', auth='none', website=False, csrf=False
    )
    def auction_live_board_data_ext(self, db_name, tournament_slug, **kw):
        """
        Override the base live-board data endpoint to inject live bid info
        (current_bid / current_bid_team) so the extended live-board template
        can display the auctioneer's last call.
        """
        from odoo.addons.auction_module.controllers.main import Auction as _Base
        base_response = _Base().auction_live_board_data(db_name, tournament_slug, **kw)

        try:
            data = json.loads(base_response.data)
        except Exception:
            return base_response

        if data.get('current_player') is not None:
            from odoo.addons.auction_module.controllers.main import Auction as _BaseCtrl
            with _BaseCtrl()._with_db(db_name) as ok:
                if ok:
                    env = request.env
                    tournament = env['auction.tournament'].sudo().search(
                        [('slug', '=', tournament_slug)], limit=1
                    )
                    t_id = tournament.id if tournament else False
                    player = env['auction.team.player'].sudo().search(
                        [('is_on_stage', '=', True), ('tournament_id', '=', t_id)], limit=1
                    )
                    if player:
                        data['current_player']['current_bid'] = player.current_bid or 0
                        if player.current_bid_team_id:
                            t = player.current_bid_team_id
                            data['current_player']['current_bid_team'] = {
                                'id': t.id,
                                'name': t.name or '',
                                'logo_url': self._pub_img('auction.team', t.id, 'logo') if t.logo else '',
                            }
                        else:
                            data['current_player']['current_bid_team'] = None

        return request.make_response(
            json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-store'),
            ],
        )

    # ── Auctioneer Console page ────────────────────────────────────────────

    @http.route('/auction/auctioneer/console', type='http', auth='user', website=False)
    def auctioneer_console_redirect(self, **kw):
        """Redirect to slug-based console URL."""
        tournament = self._resolve_tournament()
        if tournament and tournament.slug:
            return request.redirect('/auction/auctioneer/console/' + tournament.slug)
        return request.redirect('/web')

    @http.route('/auction/auctioneer/console/<string:tournament_slug>', type='http', auth='user', website=False)
    def auctioneer_console(self, tournament_slug, **kw):
        """Render the standalone Auctioneer Console page (no Odoo layout)."""
        tournament = request.env['auction.tournament'].sudo().search(
            [('slug', '=', tournament_slug)], limit=1
        )
        if not tournament:
            tournament = self._resolve_tournament()
        return request.render(
            'auction_auctioneer.auctioneer_console_template',
            {
                'tournament': tournament,
                'favicon_url': '/web/image/res.company/%d/favicon' % request.env.company.id,
            },
        )

    # ── Auctioneer Console data endpoint ──────────────────────────────────

    @http.route('/auction/auctioneer/data', type='http', auth='user', website=False, csrf=False)
    def auctioneer_data(self, **kw):
        """Return JSON payload consumed by the Auctioneer Console JS."""
        env = request.env
        tournament = self._resolve_tournament()

        result = {
            'tournament': {},
            'current_player': None,
            'teams': [],
            'slabs': [],
        }

        if tournament:
            result['tournament'] = {
                'name': tournament.name or '',
                'logo_url': self._pub_img('auction.tournament', tournament.id, 'logo') if tournament.logo else '',
            }

        # ── Current player on stage for THIS tournament ────────────────────
        current_player = env['auction.team.player'].sudo().search(
            [('is_on_stage', '=', True), ('tournament_id', '=', tournament.id if tournament else False)],
            limit=1
        )

        if current_player:
            base_price = 0
            auctions_all = env['auction.auction'].sudo().search(
                [('tournament_id', '=', tournament.id)] if tournament else []
            )
            for auc in auctions_all:
                base = self._get_effective_base(auc, current_player)
                if base > base_price:
                    base_price = base

            current_bid_team = None
            if current_player.current_bid_team_id:
                t = current_player.current_bid_team_id
                current_bid_team = {
                    'id': t.id,
                    'name': t.name or '',
                    'logo_url': self._pub_img('auction.team', t.id, 'logo') if t.logo else '',
                }

            result['current_player'] = {
                'id': current_player.id,
                'name': current_player.name or '',
                'photo_url': self._pub_img('auction.team.player', current_player.id, 'photo') if current_player.photo else '',
                'role': current_player.role or '',
                'tier_name': current_player.tier_id.name if current_player.tier_id else '',
                'tier_color': current_player.tier_color or '#2252b5',
                'state': current_player.state,
                'sl_no': current_player.sl_no or 0,
                'base_price': base_price,
                'current_bid': current_player.current_bid or 0,
                'current_bid_team': current_bid_team,
                'batting_style': current_player.batting_style or '',
                'bowling_style': current_player.bowling_style or '',
            }

        # ── Teams (strictly scoped to this tournament) ────────────────────
        auctions = env['auction.auction'].sudo().search(
            [('tournament_id', '=', tournament.id)] if tournament else [('id', '=', False)]
        )

        player = current_player if current_player else None

        for auc in auctions:
            team = auc.team_id
            if not team:
                continue

            effective_base = self._get_effective_base(auc, player)
            current_bid_val = (player.current_bid or 0) if player else 0
            next_bid_val = self._next_bid(auc, current_bid_val, effective_base)

            # Recompute max_call live using the current player's tier cap so we
            # never rely on a potentially-stale stored value when the auction is
            # in progress.
            live_max_call = auc.get_max_bid_for_team(auc, player)

            # Determine can_bid with a specific reason for the UI.
            can_bid = True
            can_bid_reason = ''

            # Resolve tier minimum bid for the current player
            _tier_base = 0
            _tier_name = ''
            if player and player.tier_id:
                _tier_name = player.tier_id.name or ''
                if auc.tier_limit_ids:
                    _tl_b = auc.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
                    _tier_base = (_tl_b[0].base_point if _tl_b and _tl_b[0].base_point > 0
                                  else (auc.base_point or 0))
                else:
                    _tier_base = auc.base_point or 0

            if not player:
                can_bid = False
                can_bid_reason = 'No player on stage'
            elif auc.remaining_players_count <= 0:
                can_bid = False
                can_bid_reason = 'Squad full'
            elif auc.remaining_points <= 0:
                can_bid = False
                can_bid_reason = 'No budget left'
            elif _tier_base > 0 and auc.remaining_points < _tier_base:
                can_bid = False
                can_bid_reason = 'Purse below %s minimum (%d pts)' % (_tier_name, _tier_base)
            elif live_max_call <= 0:
                can_bid = False
                can_bid_reason = 'Budget reserved for other players'
            elif next_bid_val > live_max_call:
                can_bid = False
                can_bid_reason = 'Max call: %d pts' % live_max_call

            if can_bid and player and player.tier_id and auc.tier_limit_ids:
                tl = auc.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
                if tl:
                    already_sold = env['auction.auction.player'].sudo().search_count([
                        ('auction_id', '=', auc.id),
                        ('player_id.tier_id', '=', player.tier_id.id),
                        ('player_id', '!=', player.id),
                    ])
                    if already_sold >= tl[0].max_players:
                        can_bid = False
                        can_bid_reason = 'Tier slot full'

            result['teams'].append({
                'id': team.id,
                'auction_id': auc.id,
                'name': team.name or '',
                'logo_url': self._pub_img('auction.team', team.id, 'logo') if team.logo else '',
                'remaining_points': auc.remaining_points,
                'total_points': auc.total_point,
                'max_call': live_max_call,
                'next_bid': next_bid_val,
                'effective_base': effective_base,
                'can_bid': can_bid,
                'can_bid_reason': can_bid_reason,
                'remaining_players': auc.remaining_players_count,
                'manager': team.manager or '',
                'slabs': [
                    {'from_amount': s.from_amount, 'increment': s.increment}
                    for s in auc.auction_bid_slab_ids.sorted('from_amount', reverse=True)
                ],
            })
            # Top-level slabs — use first auction's slabs (same tournament, same config)
            if not result['slabs'] and auc.auction_bid_slab_ids:
                result['slabs'] = [
                    {'from_amount': s.from_amount, 'increment': s.increment}
                    for s in auc.auction_bid_slab_ids.sorted('from_amount', reverse=True)
                ]

        return request.make_response(
            json.dumps(result),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-store'),
            ],
        )

    # ── Place bid ──────────────────────────────────────────────────────────

    @http.route('/auction/auctioneer/place-bid', type='json', auth='user', website=False, csrf=False)
    def place_bid(self, player_id, team_id, bid_amount, **kw):
        """Record a live bid for the current player."""
        env = request.env
        player = env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists() or not player.is_on_stage or player.state == 'sold':
            return {'success': False, 'error': 'Player is not currently available for bidding'}

        auction = env['auction.auction'].sudo().search(
            [('team_id', '=', int(team_id))], limit=1
        )
        if not auction:
            return {'success': False, 'error': 'Team not found in auction'}

        bid_amount = int(bid_amount)
        effective_base = self._get_effective_base(auction, player)

        if bid_amount < effective_base:
            return {'success': False, 'error': 'Bid is below the minimum base price of %d' % effective_base}

        # Guard: purse must cover the tier's minimum before going further
        if player.tier_id and auction.tier_limit_ids:
            _tl_base = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            _tier_min = (_tl_base[0].base_point if _tl_base and _tl_base[0].base_point > 0
                         else (auction.base_point or 0))
            if _tier_min > 0 and auction.remaining_points < _tier_min:
                return {
                    'success': False,
                    'error': 'Insufficient purse for "%s" tier (requires %d pts, team has %d pts).' % (
                        player.tier_id.name, _tier_min, auction.remaining_points
                    ),
                }

        effective_max_call = auction.get_max_bid_for_team(auction, player)
        if bid_amount > effective_max_call:
            return {
                'success': False,
                'error': 'Bid of %d exceeds max call of %d for this team' % (bid_amount, effective_max_call),
            }

        if player.tier_id and auction.tier_limit_ids:
            tl = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tl:
                already_sold = env['auction.auction.player'].sudo().search_count([
                    ('auction_id', '=', auction.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                    ('player_id', '!=', player.id),
                ])
                if already_sold >= tl[0].max_players:
                    return {
                        'success': False,
                        'error': '%s has reached the maximum of %d player(s) from the "%s" tier' % (
                            auction.team_id.name, tl[0].max_players, player.tier_id.name
                        ),
                    }

        player.sudo().write({
            'current_bid': bid_amount,
            'current_bid_team_id': int(team_id),
        })

        return {
            'success': True,
            'current_bid': bid_amount,
            'team_name': auction.team_id.name,
        }

    # ── Locked bid info (for sell modal auto-fill) ────────────────────────

    @http.route('/auction/auctioneer/locked-bid', type='http', auth='user', website=False, csrf=False)
    def locked_bid_info(self, **kw):
        """Return current_bid + current_bid_team_id for the player currently on stage."""
        tournament = self._resolve_tournament()
        t_id = tournament.id if tournament else False
        player = request.env['auction.team.player'].sudo().search(
            [('is_on_stage', '=', True), ('tournament_id', '=', t_id)], limit=1
        )
        if not player or not player.current_bid or not player.current_bid_team_id:
            return request.make_response(
                json.dumps({'current_bid': 0, 'current_bid_team_id': None}),
                headers=[('Content-Type', 'application/json')]
            )
        return request.make_response(
            json.dumps({
                'current_bid': player.current_bid,
                'current_bid_team_id': player.current_bid_team_id.id,
            }),
            headers=[('Content-Type', 'application/json')]
        )

    # ── Reset bid ──────────────────────────────────────────────────────────

    @http.route('/auction/auctioneer/reset-bid', type='json', auth='user', website=False, csrf=False)
    def reset_bid(self, player_id, **kw):
        """Reset the current live bid for the player."""
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'Player not found'}

        player.sudo().write({'current_bid': 0, 'current_bid_team_id': False})
        return {'success': True}

    # ── Finalize (sell) ────────────────────────────────────────────────────

    @http.route('/auction/auctioneer/finalize-bid', type='json', auth='user', website=False, csrf=False)
    def finalize_bid(self, player_id, **kw):
        """Sell the player to the current highest bidder and reset bid fields."""
        env = request.env
        player = env['auction.team.player'].sudo().browse(int(player_id))

        if not player.exists():
            return {'success': False, 'error': 'Player not found'}
        if not player.current_bid or not player.current_bid_team_id:
            return {'success': False, 'error': 'No bid has been placed yet'}

        result = env['auction.team.player'].sudo().action_sell_from_web(
            player.id,
            player.current_bid_team_id.id,
            player.current_bid,
        )

        if result.get('success'):
            player.sudo().write({'current_bid': 0, 'current_bid_team_id': False})

        return result

    # ── Correct live bid (auctioneer override) ────────────────────────────

    @http.route('/auction/auctioneer/correct-bid', type='json', auth='user', website=False, csrf=False)
    def correct_bid(self, new_bid, **kw):
        """Override the current live bid value without changing the leading team."""
        try:
            new_bid = int(new_bid)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'Invalid bid value'}
        if new_bid <= 0:
            return {'success': False, 'error': 'Bid must be greater than 0'}

        tournament = self._resolve_tournament()
        t_id = tournament.id if tournament else False
        player = request.env['auction.team.player'].sudo().search(
            [('is_on_stage', '=', True), ('tournament_id', '=', t_id)], limit=1
        )
        if not player:
            return {'success': False, 'error': 'No player is currently on stage'}
        if not player.current_bid_team_id:
            return {'success': False, 'error': 'No bid has been placed yet — cannot correct'}

        player.sudo().write({'current_bid': new_bid})
        return {
            'success': True,
            'current_bid': new_bid,
            'team_name': player.current_bid_team_id.name,
        }
