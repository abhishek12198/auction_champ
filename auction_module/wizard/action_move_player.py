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

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape


class AuctionMovePlayer(models.TransientModel):
    _name = 'auction.move.player'
    _description = 'Move Sold Player to Another Team'

    source_line_id = fields.Many2one(
        'auction.auction.player', string='Source Sale Line', required=True, readonly=True)
    source_player_id = fields.Many2one(
        'auction.team.player', string='Player', readonly=True)
    source_team_id = fields.Many2one('auction.team', string='Current Team', readonly=True)
    source_auction_id = fields.Many2one('auction.auction', string='Current Auction', readonly=True)
    source_points = fields.Integer(string='Current Sold Points', readonly=True)

    tournament_id = fields.Many2one('auction.tournament', string='Tournament', readonly=True)
    tournament_type = fields.Selection(
        related='tournament_id.tournament_type', string='Sport', readonly=True)
    point_unit_label = fields.Char(string='Unit', readonly=True)

    target_team_id = fields.Many2one('auction.team', string='Target Team')
    # Integer mirror so Confirm always receives the JS selection
    # (readonly Many2one widgets are often skipped on wizard save).
    selected_team_id = fields.Integer(string='Selected Team Id')
    has_target_team = fields.Boolean(string='Has Target Team')
    move_points = fields.Integer(
        string='Points on Target Team',
        help='Points assigned to this player after moving to the target team.')

    board_json = fields.Text(string='Board JSON')
    source_card_html = fields.Html(string='Source Player', sanitize=False, readonly=True)
    summary_html = fields.Html(string='Summary', sanitize=False, readonly=True)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if not active_id:
            return defaults
        line = self.env['auction.auction.player'].browse(active_id)
        if not line.exists() or not line.player_id or not line.auction_id:
            return defaults
        auction = line.auction_id
        tournament = auction.tournament_id
        unit_name = tournament.get_point_unit().name if tournament else 'Points'
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        defaults.update({
            'source_line_id': line.id,
            'source_player_id': line.player_id.id,
            'source_team_id': auction.team_id.id,
            'source_auction_id': auction.id,
            'source_points': line.points,
            'move_points': line.points,
            'tournament_id': tournament.id if tournament else False,
            'point_unit_label': unit_name,
            'source_card_html': self._render_source_card(line, auction, tournament, fmt, unit_name),
            'board_json': self._build_board_json(auction, tournament, False, fmt, unit_name),
            'summary_html': self._render_empty_summary(),
            'has_target_team': False,
        })
        return defaults

    # ── Board / HTML helpers ────────────────────────────────────────────────

    @api.model
    def _player_attrs(self, player, tournament):
        attrs = []
        if not player:
            return attrs
        is_football = bool(tournament and tournament.tournament_type == 'football')
        if is_football:
            if player.dominant_position_id:
                attrs.append({'label': 'Position', 'value': player.dominant_position_id.name})
            elif player.role:
                attrs.append({'label': 'Role', 'value': player.role})
            if player.preferred_foot:
                foot = dict(player._fields['preferred_foot'].selection).get(
                    player.preferred_foot, player.preferred_foot)
                attrs.append({'label': 'Foot', 'value': foot})
            if player.age:
                attrs.append({'label': 'Age', 'value': str(player.age)})
            if player.height:
                attrs.append({'label': 'Height', 'value': player.height})
            if player.use_other_attributes:
                for attr in player.other_attribute_ids:
                    label = (attr.label or '').strip()
                    value = (attr.value or '').strip()
                    if label and value:
                        attrs.append({'label': label, 'value': value})
        else:
            if player.role:
                attrs.append({'label': 'Role', 'value': player.role})
            if player.batting_style:
                attrs.append({'label': 'Batting', 'value': player.batting_style})
            if player.bowling_style:
                attrs.append({'label': 'Bowling', 'value': player.bowling_style})
        return attrs

    @api.model
    def _build_board_json(self, source_auction, tournament, target_team, fmt, unit_name):
        auctions = self.env['auction.auction'].search([
            ('tournament_id', '=', tournament.id if tournament else False),
            ('team_id', '!=', False),
            ('id', '!=', source_auction.id),
        ], order='id')
        selected_team_id = target_team.id if target_team else False
        teams = []
        for auc in auctions:
            team = auc.team_id
            if not team:
                continue
            teams.append({
                'team_id': team.id,
                'name': team.name or '',
                'logo_url': '/web/image/auction.team/%d/logo' % team.id if team.logo else '',
                'player_count': len(auc.player_ids),
                'remaining_points_label': fmt(auc.remaining_points or 0),
                'max_players': auc.max_players or 0,
                'selected': bool(selected_team_id and team.id == selected_team_id),
            })
        return json.dumps({
            'unit_label': unit_name or 'Points',
            'sport': (tournament.tournament_type if tournament else 'cricket') or 'cricket',
            'source_team_id': source_auction.team_id.id if source_auction.team_id else False,
            'selected_team_id': selected_team_id or False,
            'teams': teams,
        })

    @api.model
    def action_get_move_board(self, source_auction_id, target_team_id=False):
        auction = self.env['auction.auction'].browse(int(source_auction_id or 0))
        if not auction.exists():
            return json.dumps({'teams': [], 'unit_label': 'Points', 'sport': 'cricket'})
        tournament = auction.tournament_id
        unit_name = tournament.get_point_unit().name if tournament else 'Points'
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        target_team = self.env['auction.team'].browse(int(target_team_id or 0))
        if not target_team.exists():
            target_team = self.env['auction.team']
        return self._build_board_json(auction, tournament, target_team, fmt, unit_name)

    @api.model
    def _render_source_card(self, line, auction, tournament, fmt, unit_name):
        p = line.player_id
        team = auction.team_id
        attrs = self._player_attrs(p, tournament)
        attr_html = ''.join(
            '<span class="ac-swap-chip"><b>%s</b> %s</span>' % (
                html_escape(a['label']), html_escape(a['value']))
            for a in attrs
        )
        contact = html_escape(p.contact or '—')
        role = html_escape(p.role or '—')
        tier = html_escape(line.tier_id.name if line.tier_id else '—')
        tier_color = html_escape(line.tier_color or '#3498db')
        team_name = html_escape(team.name if team else '—')
        points_label = html_escape(fmt(line.points or 0))
        unit = html_escape(unit_name or 'Points')
        sport = (tournament.tournament_type if tournament else 'cricket') or 'cricket'
        icon_badge = '<span class="ac-swap-icon-badge">★ ICON</span>' if line.icon_player else ''
        return '''
<div class="ac-swap-source" data-sport="%s">
  <div class="ac-swap-source-label">Player to move</div>
  <div class="ac-swap-source-card">
    <div class="ac-swap-photo">
      <img src="/web/image/auction.team.player/%d/photo" alt=""/>
    </div>
    <div class="ac-swap-source-body">
      <div class="ac-swap-source-top">
        <div>
          <div class="ac-swap-name">%s</div>
          <div class="ac-swap-meta">%s · %s</div>
        </div>
        %s
      </div>
      <div class="ac-swap-source-stats">
        <div class="ac-swap-stat">
          <span class="ac-swap-stat-label">Current team</span>
          <span class="ac-swap-stat-value">%s</span>
        </div>
        <div class="ac-swap-stat">
          <span class="ac-swap-stat-label">Sold for</span>
          <span class="ac-swap-stat-value ac-swap-pts">%s <small>%s</small></span>
        </div>
        <div class="ac-swap-stat">
          <span class="ac-swap-stat-label">Tier</span>
          <span class="ac-swap-stat-value">
            <span class="ac-swap-tier" style="background:%s">%s</span>
          </span>
        </div>
        <div class="ac-swap-stat">
          <span class="ac-swap-stat-label">Mobile</span>
          <span class="ac-swap-stat-value">%s</span>
        </div>
      </div>
      <div class="ac-swap-attrs">%s</div>
    </div>
  </div>
</div>
''' % (
            html_escape(sport), p.id, html_escape(p.name or 'Player'), role, unit,
            icon_badge, team_name, points_label, unit, tier_color, tier, contact, attr_html,
        )

    @api.model
    def _render_empty_summary(self):
        return (
            '<div class="ac-swap-summary ac-swap-summary-empty">'
            'Select a target team to preview the move.'
            '</div>'
        )

    def _render_summary(self):
        self.ensure_one()
        if not self.target_team_id:
            return self._render_empty_summary()
        tournament = self.tournament_id
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        unit = html_escape(self.point_unit_label or 'Points')
        return '''
<div class="ac-swap-summary">
  <div class="ac-swap-summary-title">Move preview</div>
  <div class="ac-swap-summary-grid">
    <div class="ac-swap-summary-item">
      <div class="ac-swap-summary-arrow">→</div>
      <div>
        <strong>%s</strong> moves from <strong>%s</strong> to <strong>%s</strong>
        for <span class="ac-swap-pts">%s</span> %s
      </div>
    </div>
  </div>
</div>
''' % (
            html_escape(self.source_player_id.name or ''),
            html_escape(self.source_team_id.name or ''),
            html_escape(self.target_team_id.name or ''),
            html_escape(fmt(self.move_points or 0)),
            unit,
        )

    def _refresh_board(self):
        self.ensure_one()
        auction = self.source_auction_id
        tournament = self.tournament_id
        unit_name = self.point_unit_label or 'Points'
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        self.board_json = self._build_board_json(
            auction, tournament, self.target_team_id, fmt, unit_name)
        self.summary_html = self._render_summary()

    @api.onchange('target_team_id')
    def _onchange_target_team_id(self):
        self.has_target_team = bool(self.target_team_id)
        self.selected_team_id = self.target_team_id.id if self.target_team_id else 0
        if not self.move_points:
            self.move_points = self.source_points
        self._refresh_board()

    @api.onchange('selected_team_id')
    def _onchange_selected_team_id(self):
        team = self.env['auction.team'].browse(self.selected_team_id or 0)
        if team.exists():
            self.target_team_id = team
            self.has_target_team = True
            if not self.move_points:
                self.move_points = self.source_points
            self._refresh_board()
        elif not self.selected_team_id:
            self.target_team_id = False
            self.has_target_team = False
            self._refresh_board()

    @api.onchange('move_points')
    def _onchange_move_points(self):
        self.summary_html = self._render_summary()

    def _resolve_target_team(self):
        """Resolve destination team from saved fields or board_json selection."""
        self.ensure_one()
        if self.target_team_id:
            return self.target_team_id
        if self.selected_team_id:
            team = self.env['auction.team'].browse(int(self.selected_team_id))
            if team.exists():
                return team
        if self.board_json:
            try:
                data = json.loads(self.board_json)
            except (TypeError, ValueError):
                data = {}
            tid = data.get('selected_team_id') or False
            if tid:
                team = self.env['auction.team'].browse(int(tid))
                if team.exists():
                    return team
        return self.env['auction.team']

    def _assert_tier_capacity(self, auction, players):
        for tl in auction.tier_limit_ids:
            if not tl.max_players:
                continue
            count = len(players.filtered(lambda p: p.tier_id.id == tl.tier_id.id))
            if count > tl.max_players:
                raise UserError(_(
                    '"%(team)s" would have %(count)s players in tier "%(tier)s" '
                    '(limit %(max)s). Adjust the move or tier limits first.'
                ) % {
                    'team': auction.team_id.name,
                    'count': count,
                    'tier': tl.tier_id.name,
                    'max': tl.max_players,
                })

    def action_confirm_move(self):
        self.ensure_one()
        if not self.source_line_id or not self.source_player_id:
            raise UserError(_('Source player is missing.'))

        target_team = self._resolve_target_team()
        if not target_team:
            raise UserError(_('Please select a target team.'))
        # Persist resolved team on the wizard row for consistency
        if self.target_team_id != target_team:
            self.target_team_id = target_team
            self.selected_team_id = target_team.id

        source_auction = self.source_line_id.auction_id
        target_auction = self.env['auction.auction'].search([
            ('team_id', '=', target_team.id),
            ('tournament_id', '=', self.tournament_id.id),
        ], limit=1)
        if not source_auction or not target_auction:
            raise UserError(_('Auction records for one of the teams could not be found.'))
        if source_auction.id == target_auction.id:
            raise UserError(_('Player is already on this team.'))

        move_points = int(self.move_points or 0)
        if move_points < 0:
            raise UserError(_('Points cannot be negative.'))

        player = self.source_player_id

        # Target team budget: add this player at move_points
        spent_b = sum(target_auction.player_ids.mapped('points')) + move_points
        if spent_b > (target_auction.total_point or 0):
            raise UserError(_(
                '"%(team)s" would exceed its budget after the move '
                '(spent %(spent)s / budget %(budget)s).'
            ) % {
                'team': target_auction.team_id.name,
                'spent': spent_b,
                'budget': target_auction.total_point,
            })

        # Max players on target team
        if target_auction.max_players and len(target_auction.player_ids) >= target_auction.max_players:
            raise UserError(_(
                '"%(team)s" already has the maximum number of players (%(max)s).'
            ) % {
                'team': target_auction.team_id.name,
                'max': target_auction.max_players,
            })

        target_players_after = target_auction.player_ids.mapped('player_id') | player
        self._assert_tier_capacity(target_auction, target_players_after)

        self.source_line_id.write({
            'auction_id': target_auction.id,
            'points': move_points,
        })
        player.assigned_team_id = target_auction.team_id

        tournament = self.tournament_id
        fmt = (tournament.format_points if tournament
               else (lambda n: '{:,}'.format(int(n or 0))))
        msg = '%s moved to %s for %s (from %s)' % (
            player.name, target_auction.team_id.name, fmt(move_points), source_auction.team_id.name)
        player.create_auction_history(
            target_auction.team_id.id, msg,
            tournament_id=tournament.id if tournament else False, player=player)

        self.env.user.notify_success(
            message='%s moved to %s.' % (player.name, target_auction.team_id.name),
            title='Player Moved',
        )
        return {'type': 'ir.actions.act_window_close'}
