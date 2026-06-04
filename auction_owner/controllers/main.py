# -*- coding: utf-8 -*-
import json
import logging

from odoo import fields as odoo_fields, http
from odoo.http import request
from odoo.addons.web.controllers.main import Home

_logger = logging.getLogger(__name__)


# ── Login redirect: send Owner users straight to the Owner Console ─────────────
class AuctionOwnerHome(Home):
    @http.route('/web', type='http', auth='none')
    def web_client(self, s_action=None, **kw):
        if request.session.uid:
            try:
                user = request.env['res.users'].sudo().browse(request.session.uid)
                if user.has_group('auction_owner.group_auction_owner'):
                    return request.redirect('/auction/owner/console', 303)
            except Exception:
                pass
        return super().web_client(s_action=s_action, **kw)


class AuctionOwnerController(http.Controller):

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _pub_img(model, record_id, field):
        return '/auction/public/image/%s/%d/%s' % (model, record_id, field)

    @staticmethod
    def _get_effective_base(auction, player):
        if player and player.tier_id and auction.tier_limit_ids:
            tl = auction.tier_limit_ids.filtered(
                lambda l: l.tier_id.id == player.tier_id.id
            )
            if tl and tl[0].base_point > 0:
                return tl[0].base_point
        return auction.base_point

    @staticmethod
    def _next_bid(auction, current_bid, effective_base):
        if current_bid == 0:
            return effective_base
        slabs = auction.auction_bid_slab_ids.sorted('from_amount', reverse=True)
        for slab in slabs:
            if current_bid >= slab.from_amount:
                return current_bid + slab.increment
        return current_bid + 1

    def _squad_for_auction(self, auction):
        """Return a list of player dicts for the given auction record."""
        env = request.env
        ap_records = env['auction.auction.player'].sudo().search(
            [('auction_id', '=', auction.id)]
        )
        squad = []
        for ap in ap_records:
            p = ap.player_id
            squad.append({
                'id': p.id,
                'name': p.name or '',
                'photo_url': self._pub_img('auction.team.player', p.id, 'photo') if p.photo else '',
                'role': p.role or '',
                'tier_name': p.tier_id.name if p.tier_id else '',
                'tier_color': p.tier_id.color if p.tier_id else '#3498db',
                'points': ap.points or 0,
            })
        return squad

    def _team_payload(self, auc, player, include_squad=False):
        """Build a team data dict for the given auction record."""
        team = auc.team_id
        effective_base = self._get_effective_base(auc, player)
        current_bid_val = (player.current_bid or 0) if player else 0
        next_bid_val = self._next_bid(auc, current_bid_val, effective_base)
        live_max_call = auc.get_max_bid_for_team(auc)

        can_bid = True
        can_bid_reason = ''

        if not player:
            can_bid = False
            can_bid_reason = 'No player on stage'
        elif auc.remaining_players_count <= 0:
            can_bid = False
            can_bid_reason = 'Squad full'
        elif auc.remaining_points <= 0:
            can_bid = False
            can_bid_reason = 'No budget left'
        elif live_max_call <= 0:
            can_bid = False
            can_bid_reason = 'Budget reserved for other players'
        elif next_bid_val > live_max_call:
            can_bid = False
            can_bid_reason = 'Max call: %d pts' % live_max_call

        # Current-bid restriction: owner cannot raise their own bid
        if can_bid and player and player.current_bid_team_id and \
                player.current_bid_team_id.id == team.id:
            can_bid = False
            can_bid_reason = 'You have the current bid — wait for a rival'

        if can_bid and player and player.tier_id and auc.tier_limit_ids:
            tl = auc.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tl:
                already_sold = request.env['auction.auction.player'].sudo().search_count([
                    ('auction_id', '=', auc.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                ])
                if already_sold >= tl[0].max_players:
                    can_bid = False
                    can_bid_reason = 'Tier slot full'

        payload = {
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
            'player_count': len(auc.player_ids),
            'max_players': auc.max_players,
            'manager': team.manager or '',
        }
        if include_squad:
            payload['squad'] = self._squad_for_auction(auc)
        return payload

    # ── Owner Console page ─────────────────────────────────────────────────

    @http.route('/auction/owner/console', type='http', auth='user', website=False)
    def owner_console(self, **kw):
        user = request.env.user
        if not user.has_group('auction_owner.group_auction_owner'):
            return request.not_found()

        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        return request.render(
            'auction_owner.owner_console_template',
            {'tournament': tournament, 'user': user},
        )

    # ── Owner Console data endpoint ────────────────────────────────────────

    @http.route('/auction/owner/data', type='http', auth='user', website=False, csrf=False)
    def owner_data(self, **kw):
        user = request.env.user.sudo()
        env = request.env

        tournament = env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )

        result = {
            'tournament': {},
            'current_player': None,
            'my_team': None,
            'teams': [],
            'slabs': [],
            'presets': [],
            'owner': {'name': user.name or '', 'login': user.login or ''},
        }

        if tournament:
            result['tournament'] = {
                'name': tournament.name or '',
                'theme': tournament.player_display_template or 'vanilla',
                'logo_url': self._pub_img('auction.tournament', tournament.id, 'logo') if tournament.logo else '',
            }
            if tournament.preset_points:
                try:
                    result['presets'] = [
                        int(x.strip())
                        for x in tournament.preset_points.split(',')
                        if x.strip().lstrip('-').isdigit()
                    ]
                except Exception:
                    pass

        # ── Current player on stage ────────────────────────────────────────
        current_player = env['auction.team.player'].sudo().search(
            [('is_on_stage', '=', True)], limit=1
        )

        if current_player:
            base_price = 0
            auc_domain = [('tournament_id', '=', tournament.id)] if tournament else []
            auctions_all = env['auction.auction'].sudo().search(auc_domain) or \
                           env['auction.auction'].sudo().search([])
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

        # ── Teams ─────────────────────────────────────────────────────────
        auc_domain = [('tournament_id', '=', tournament.id)] if tournament else []
        auctions = env['auction.auction'].sudo().search(auc_domain) or \
                   env['auction.auction'].sudo().search([])

        my_team_id = user.auction_team_id.id if user.auction_team_id else False

        for auc in auctions:
            if not auc.team_id:
                continue
            is_mine = (auc.team_id.id == my_team_id)
            payload = self._team_payload(auc, current_player, include_squad=True)
            if is_mine:
                result['my_team'] = payload
                # Expose this auction's bid slabs so the frontend can compute
                # slab-aware step increments for the +/- bid buttons.
                result['slabs'] = [
                    {
                        'from_amount': s.from_amount,
                        'to_amount': s.to_amount,
                        'increment': s.increment,
                    }
                    for s in auc.auction_bid_slab_ids.sorted('from_amount', reverse=True)
                ]
            result['teams'].append(payload)

        result['counter'] = {
            'started_at': (
                tournament.counter_started_at.isoformat()
                if tournament and tournament.counter_started_at else None
            ),
            'hammer_count': tournament.hammer_count if tournament else 3,
            'age_seconds': (
                (odoo_fields.Datetime.now() - tournament.counter_started_at).total_seconds()
                if tournament and tournament.counter_started_at else None
            ),
        }

        return request.make_response(
            json.dumps(result),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-store'),
            ],
        )

    # ── Counter check (polled by owner consoles every 2 s) ─────────────────

    @http.route('/auction/owner/counter-check', type='http', auth='public',
                website=False, csrf=False, methods=['GET'])
    def counter_check(self, **kw):
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        result = {'started_at': None, 'hammer_count': 3, 'age_seconds': None}
        if tournament and tournament.counter_started_at:
            result['started_at']   = tournament.counter_started_at.isoformat()
            result['hammer_count'] = tournament.hammer_count or 3
            result['age_seconds']  = (
                odoo_fields.Datetime.now() - tournament.counter_started_at
            ).total_seconds()
        return request.make_response(
            json.dumps(result),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-store'),
            ],
        )

    # ── Enable Counter ──────────────────────────────────────────────────────

    @http.route('/auction/owner/enable-counter', type='http', auth='public',
                website=True, csrf=False, methods=['POST'])
    def enable_counter(self, **kw):
        tournament = request.env['auction.tournament'].sudo().search(
            [('active', '=', True)], limit=1
        )
        if tournament:
            tournament.sudo().write({'counter_started_at': odoo_fields.Datetime.now()})
        return request.make_response(
            json.dumps({'ok': bool(tournament)}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Place bid ──────────────────────────────────────────────────────────

    @http.route('/auction/owner/place-bid', type='json', auth='user', website=False, csrf=False)
    def place_bid(self, player_id, team_id, bid_amount, **kw):
        user = request.env.user.sudo()
        env = request.env

        # Owners can only bid for their own assigned team
        if not user.auction_team_id or user.auction_team_id.id != int(team_id):
            return {'success': False, 'error': 'You can only bid for your own team.'}

        player = env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists() or not player.is_on_stage:
            return {'success': False, 'error': 'Player is not currently on stage.'}

        if player.current_bid_team_id and player.current_bid_team_id.id == int(team_id):
            return {'success': False, 'error': 'You already have the highest bid. Wait for another team to bid.'}

        auction = env['auction.auction'].sudo().search(
            [('team_id', '=', int(team_id))], limit=1
        )
        if not auction:
            return {'success': False, 'error': 'Auction record not found for your team.'}

        bid_amount = int(bid_amount)
        effective_base = self._get_effective_base(auction, player)

        if bid_amount < effective_base:
            return {'success': False, 'error': 'Bid must be at least %d pts (base price).' % effective_base}

        live_max_call = auction.get_max_bid_for_team(auction)
        if bid_amount > live_max_call:
            return {'success': False, 'error': 'Bid of %d exceeds your max call of %d pts.' % (bid_amount, live_max_call)}

        if player.tier_id and auction.tier_limit_ids:
            tl = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tl:
                already_sold = env['auction.auction.player'].sudo().search_count([
                    ('auction_id', '=', auction.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                ])
                if already_sold >= tl[0].max_players:
                    return {
                        'success': False,
                        'error': 'Your team has reached the max players for the "%s" tier.' % player.tier_id.name,
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
