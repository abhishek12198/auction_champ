# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################
"""Env-parameterized builders for the three public live poll payloads.

Reuses projector/live-board/balance logic from the HTTP controllers without
binding to ``request.env``, so postcommit rebuilds can run on a fresh cursor.
"""
import json
import logging
import time
from datetime import datetime

import pytz

from odoo import fields

_logger = logging.getLogger(__name__)


def _stamp_iso(tournament):
    if not tournament or not tournament.stamp_expires_at:
        return None
    try:
        return fields.Datetime.to_string(tournament.stamp_expires_at)
    except Exception:
        return str(tournament.stamp_expires_at)


def _helpers():
    from odoo.addons.auction_module.controllers import main as ctrl
    return ctrl


def build_live_board_payload(env, tournament, db_name):
    """Public live-board JSON dict. Extra ``seq`` / ``stamp_expires_at`` are additive."""
    ctrl = _helpers()
    pub_img = lambda model, record_id, field: (
        '/%s/auction/public/image/%s/%d/%s' % (db_name, model, record_id, field)
    )
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

    stamp_player = None
    now_dt = fields.Datetime.now()
    if tournament.stamp_expires_at and tournament.stamp_expires_at > now_dt and tournament.stamp_player_id:
        stamp_player = tournament.stamp_player_id

    on_stage = env['auction.team.player'].sudo().search([
        ('is_on_stage', '=', True),
        ('tournament_id', '=', tournament.id),
    ], limit=1)
    # Match projector: a new auction player on stage wins over a stale SOLD/UNSOLD
    # stamp from the previous player. Otherwise the live board stays on the sold
    # face until the next sale even after the operator calls the next player.
    current_player = None
    if (on_stage and on_stage.state == 'auction'
            and (not stamp_player or stamp_player.id != on_stage.id)):
        current_player = on_stage
    elif stamp_player:
        current_player = stamp_player
    elif on_stage:
        current_player = on_stage

    if current_player:
        result['no_auction'] = False
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
        result['current_player'].update(ctrl._football_display_payload(current_player))
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

    history = env['auction.history'].sudo().search(
        [('tournament_id', '=', tournament.id)], order='create_date desc', limit=5
    )
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

    is_football = (tournament.tournament_type == 'football')
    auctions = env['auction.auction'].sudo().search(
        [('tournament_id', '=', tournament.id)]
    )
    auctions.mapped('player_ids.player_id.tier_id')
    auctions.mapped('player_ids.player_id.dominant_position_id')
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
                        parts = [w for w in pos_name.replace('-', ' ').split() if w]
                        pos_code = ''.join(w[0] for w in parts).upper()[:3]
                entry = {
                    'name': p.name or '',
                    'photo_url': pub_img('auction.team.player', p.id, 'photo') if p.photo else '',
                    'role': p.role or '',
                    'position_code': pos_code,
                    'position_name': pos_name,
                    'points': line.points,
                }
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

    counts = ctrl._pj_player_state_counts(tournament, env=env)
    result['stats'] = {
        'in_auction': counts['auction'],
        'sold': counts['sold'],
        'unsold': counts['unsold'],
        'total': sum(counts.values()),
    }
    result['wait_phase'] = ctrl._pj_wait_phase(tournament, audience='viewers', env=env)
    result['stamp_expires_at'] = _stamp_iso(tournament)
    result['stamp_state'] = (tournament.stamp_state if tournament else None) or None
    result['live_board_active'] = bool(tournament.live_board_active) if tournament else False
    return result


def build_projector_payload(env, tournament, db_name):
    """Projector JSON dict (type='json' route). Additive seq/stamp keys only."""
    ctrl = _helpers()
    now_dt = datetime.now(pytz.utc).replace(tzinfo=None)
    boards = ctrl._pj_boards(tournament, db_name, env=env)
    player = None
    state_override = None
    stamp_player = None
    if (tournament and tournament.stamp_expires_at
            and tournament.stamp_expires_at > now_dt
            and tournament.stamp_player_id):
        stamp_player = tournament.stamp_player_id

    domain = [('is_on_stage', '=', True)]
    if tournament:
        domain.append(('tournament_id', '=', tournament.id))
    on_stage = env['auction.team.player'].sudo().search(domain, limit=1)

    dice_state = tournament.dice_state if tournament else 'idle'
    raw_dice = int(tournament.dice_result or 0) if tournament else 0
    dice_mystery = raw_dice < 0
    lookup_sl = abs(raw_dice) if raw_dice else 0
    dice_result = 0 if dice_mystery else lookup_sl
    if tournament and lookup_sl and not dice_mystery:
        dice_player = env['auction.team.player'].sudo().search([
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

    def _idle():
        return {
            'player': None,
            'dice': dice_payload,
            'progress': ctrl._pj_progress(tournament, env=env),
            'wait_phase': ctrl._pj_wait_phase(tournament, env=env),
            'teams': ctrl._pj_teams(tournament, db_name, env=env),
            'recent_bids': ctrl._pj_recent_bids(tournament, db_name, env=env),
            'top_purse': ctrl._pj_top_purse(tournament, env=env),
            'auction_meta': ctrl._pj_auction_meta(tournament),
            'break_time': bool(tournament and tournament.break_time_active),
            'advertisers': ctrl._pj_advertisers(tournament, db_name),
            'boards': boards,
            'stamp_expires_at': _stamp_iso(tournament),
            'stamp_state': (tournament.stamp_state if tournament else None) or None,
        }

    if dice_state == 'rolling':
        return _idle()

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
        return _idle()

    photo = ''
    photo_url = ''
    if player.photo:
        photo_url = ctrl._pj_player_photo_url(db_name, player)
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
        auction_line = env['auction.auction.player'].sudo().search(
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
    player_payload.update(ctrl._football_display_payload(player))
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
        'progress': ctrl._pj_progress(tournament, current_player=player, env=env),
        'wait_phase': ctrl._pj_wait_phase(tournament, env=env),
        'teams': ctrl._pj_teams(tournament, db_name, leading_team_id=leading_team_id, env=env),
        'recent_bids': ctrl._pj_recent_bids(tournament, db_name, player=player, env=env),
        'top_purse': ctrl._pj_top_purse(tournament, env=env),
        'auction_meta': ctrl._pj_auction_meta(tournament),
        'break_time': bool(tournament and tournament.break_time_active),
        'advertisers': ctrl._pj_advertisers(tournament, db_name),
        'boards': boards,
        'stamp_expires_at': _stamp_iso(tournament),
        'stamp_state': (tournament.stamp_state if tournament else None) or None,
    }


def build_balance_payload(env, tournament):
    """Bid Summary JSON dict. ``max_call`` is computed here, not on every viewer poll
    when Redis serves the snapshot.
    """
    Auction = env['auction.auction'].sudo().with_context(
        auction_skip_tournament_security=True,
        active_test=True,
    )
    auctions = Auction.search([
        '|',
        ('tournament_id', '=', tournament.id),
        ('team_id.tournament_id', '=', tournament.id),
    ])
    auctions.mapped('player_ids.tier_id')
    auctions.mapped('tier_limit_ids.tier_id')
    auctions.mapped('auction_bid_slab_ids')
    Player = env['auction.team.player'].sudo().with_context(
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
    return {'teams': teams_data}


def attach_seq(payload, seq):
    if payload is None:
        return None
    payload = dict(payload)
    payload['seq'] = int(seq or 0)
    return payload
