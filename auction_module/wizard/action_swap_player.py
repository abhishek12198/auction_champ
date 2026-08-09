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


class AuctionSwapPlayer(models.TransientModel):
    _name = 'auction.swap.player'
    _description = 'Swap Sold Players Between Teams'

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

    target_team_id = fields.Many2one(
        'auction.team', string='Target Team',
        help='Team that will receive the source player after the swap.')
    target_auction_id = fields.Many2one(
        'auction.auction', string='Target Auction', compute='_compute_target_auction', store=False)
    target_line_id = fields.Integer(
        string='Selected Target Sale Line',
        help='Technical id of auction.auction.player on the target team.')
    target_player_id = fields.Many2one(
        'auction.team.player', string='Swap With Player', readonly=True)
    target_points = fields.Integer(string='Target Current Points', readonly=True)
    has_target_player = fields.Boolean(string='Has Target Player')

    source_swap_points = fields.Integer(
        string='Points for Source Player on Target Team',
        help='Points assigned to the source player after moving to the target team.')
    target_swap_points = fields.Integer(
        string='Points for Target Player on Current Team',
        help='Points assigned to the selected target player after moving to the source team.')

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
            'source_swap_points': line.points,
            'tournament_id': tournament.id if tournament else False,
            'point_unit_label': unit_name,
            'source_card_html': self._render_source_card(line, auction, tournament, fmt, unit_name),
            'board_json': self._build_board_json(auction, tournament, False, False, fmt, unit_name),
            'summary_html': self._render_empty_summary(),
        })
        return defaults

    @api.depends('target_team_id', 'tournament_id')
    def _compute_target_auction(self):
        for wiz in self:
            auction = False
            if wiz.target_team_id and wiz.tournament_id:
                auction = self.env['auction.auction'].search([
                    ('team_id', '=', wiz.target_team_id.id),
                    ('tournament_id', '=', wiz.tournament_id.id),
                ], limit=1)
            wiz.target_auction_id = auction

    # ── Board / HTML helpers ────────────────────────────────────────────────

    @api.model
    def _player_attrs(self, player, tournament):
        """Sport-aware attribute chips for the custom board."""
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
                styles = player.playing_style_ids.mapped('name')
                if styles:
                    attrs.append({'label': 'Style', 'value': ', '.join(styles[:3])})
        else:
            if player.role:
                attrs.append({'label': 'Role', 'value': player.role})
            if player.batting_style:
                attrs.append({'label': 'Batting', 'value': player.batting_style})
            if player.bowling_style:
                attrs.append({'label': 'Bowling', 'value': player.bowling_style})
        return attrs

    @api.model
    def _build_board_json(self, source_auction, tournament, target_team, selected_line_id, fmt, unit_name):
        Auction = self.env['auction.auction']
        teams = []
        auctions = Auction.search([
            ('tournament_id', '=', tournament.id if tournament else False),
            ('team_id', '!=', False),
            ('id', '!=', source_auction.id),
        ], order='id')
        selected_team_id = target_team.id if target_team else False
        for auc in auctions:
            team = auc.team_id
            if not team:
                continue
            players = []
            if selected_team_id and team.id == selected_team_id:
                for pline in auc.player_ids.sorted(lambda l: (-(l.points or 0), l.player_id.name or '')):
                    p = pline.player_id
                    if not p:
                        continue
                    players.append({
                        'line_id': pline.id,
                        'player_id': p.id,
                        'name': p.name or '',
                        'role': p.role or '',
                        'contact': p.contact or '',
                        'points': pline.points or 0,
                        'points_label': fmt(pline.points or 0),
                        'tier': pline.tier_id.name if pline.tier_id else '',
                        'tier_color': pline.tier_color or '#3498db',
                        'icon': bool(pline.icon_player),
                        'photo_url': '/web/image/auction.team.player/%d/photo' % p.id,
                        'attrs': self._player_attrs(p, tournament),
                        'selected': bool(selected_line_id and pline.id == selected_line_id),
                    })
            teams.append({
                'team_id': team.id,
                'name': team.name or '',
                'logo_url': '/web/image/auction.team/%d/logo' % team.id if team.logo else '',
                'player_count': len(auc.player_ids),
                'remaining_points_label': fmt(auc.remaining_points or 0),
                'selected': bool(selected_team_id and team.id == selected_team_id),
                'players': players,
            })
        return json.dumps({
            'unit_label': unit_name or 'Points',
            'sport': (tournament.tournament_type if tournament else 'cricket') or 'cricket',
            'source_team_id': source_auction.team_id.id if source_auction.team_id else False,
            'selected_team_id': selected_team_id or False,
            'selected_line_id': selected_line_id or False,
            'teams': teams,
        })

    @api.model
    def action_get_swap_board(self, source_auction_id, target_team_id=False, selected_line_id=0):
        """RPC helper used by the custom board widget to reload team players."""
        auction = self.env['auction.auction'].browse(int(source_auction_id or 0))
        if not auction.exists():
            return json.dumps({'teams': [], 'unit_label': 'Points', 'sport': 'cricket'})
        tournament = auction.tournament_id
        unit_name = tournament.get_point_unit().name if tournament else 'Points'
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        target_team = self.env['auction.team'].browse(int(target_team_id or 0))
        if not target_team.exists():
            target_team = self.env['auction.team']
        return self._build_board_json(
            auction,
            tournament,
            target_team,
            int(selected_line_id or 0),
            fmt,
            unit_name,
        )

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
            html_escape(sport),
            p.id,
            html_escape(p.name or 'Player'),
            role,
            html_escape(unit),
            icon_badge,
            team_name,
            points_label,
            unit,
            tier_color,
            tier,
            contact,
            attr_html,
        )

    @api.model
    def _render_empty_summary(self):
        return (
            '<div class="ac-swap-summary ac-swap-summary-empty">'
            'Select a target team and a player to preview the swap.'
            '</div>'
        )

    def _render_summary(self):
        self.ensure_one()
        if not self.target_team_id or not self.target_player_id:
            return self._render_empty_summary()
        tournament = self.tournament_id
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        unit = html_escape(self.point_unit_label or 'Points')
        return '''
<div class="ac-swap-summary">
  <div class="ac-swap-summary-title">Swap preview</div>
  <div class="ac-swap-summary-grid">
    <div class="ac-swap-summary-item">
      <div class="ac-swap-summary-arrow">→</div>
      <div>
        <strong>%s</strong> moves to <strong>%s</strong>
        for <span class="ac-swap-pts">%s</span> %s
      </div>
    </div>
    <div class="ac-swap-summary-item">
      <div class="ac-swap-summary-arrow">←</div>
      <div>
        <strong>%s</strong> moves to <strong>%s</strong>
        for <span class="ac-swap-pts">%s</span> %s
      </div>
    </div>
  </div>
</div>
''' % (
            html_escape(self.source_player_id.name or ''),
            html_escape(self.target_team_id.name or ''),
            html_escape(fmt(self.source_swap_points or 0)),
            unit,
            html_escape(self.target_player_id.name or ''),
            html_escape(self.source_team_id.name or ''),
            html_escape(fmt(self.target_swap_points or 0)),
            unit,
        )

    def _refresh_board(self):
        self.ensure_one()
        auction = self.source_auction_id
        tournament = self.tournament_id
        unit_name = self.point_unit_label or 'Points'
        fmt = tournament.format_points if tournament else (lambda n: '{:,}'.format(int(n or 0)))
        self.board_json = self._build_board_json(
            auction, tournament, self.target_team_id, self.target_line_id, fmt, unit_name)
        self.summary_html = self._render_summary()

    # ── Onchanges ───────────────────────────────────────────────────────────

    @api.onchange('target_team_id')
    def _onchange_target_team_id(self):
        # If a player line already belongs to this team, keep it (player click
        # must not be wiped when team is re-asserted in the same change set).
        line = self.env['auction.auction.player'].browse(self.target_line_id or 0)
        keep = (
            bool(self.target_team_id)
            and line.exists()
            and line.auction_id.team_id.id == self.target_team_id.id
        )
        if keep:
            self.target_player_id = line.player_id
            self.target_points = line.points
            self.has_target_player = True
            if not self.target_swap_points:
                self.target_swap_points = line.points
            if not self.source_swap_points:
                self.source_swap_points = self.source_points
            self._refresh_board()
            return

        self.target_line_id = 0
        self.target_player_id = False
        self.target_points = 0
        self.target_swap_points = 0
        self.has_target_player = False
        if self.source_points and not self.source_swap_points:
            self.source_swap_points = self.source_points
        self._refresh_board()

    @api.onchange('target_line_id')
    def _onchange_target_line_id(self):
        line = self.env['auction.auction.player'].sudo().browse(self.target_line_id or 0)
        if not line.exists():
            self.target_player_id = False
            self.target_points = 0
            self.target_swap_points = 0
            self.has_target_player = False
            self.summary_html = self._render_empty_summary()
            return
        if self.target_team_id and line.auction_id.team_id != self.target_team_id:
            self.target_line_id = 0
            self.target_player_id = False
            self.target_points = 0
            self.target_swap_points = 0
            self.has_target_player = False
            self.summary_html = self._render_empty_summary()
            return
        self.target_player_id = line.player_id
        self.target_points = line.points
        self.has_target_player = True
        self.target_swap_points = line.points
        if not self.source_swap_points:
            self.source_swap_points = self.source_points
        # Refresh summary only — do not rebuild board_json (JS already marked selection)
        self.summary_html = self._render_summary()

    @api.onchange('source_swap_points', 'target_swap_points')
    def _onchange_swap_points(self):
        self.summary_html = self._render_summary()

    # ── Validation & confirm ────────────────────────────────────────────────

    def _assert_tier_capacity(self, auction, players):
        """Raise if post-swap roster would break per-tier max_players."""
        for tl in auction.tier_limit_ids:
            if not tl.max_players:
                continue
            count = len(players.filtered(lambda p: p.tier_id.id == tl.tier_id.id))
            if count > tl.max_players:
                raise UserError(_(
                    '"%(team)s" would have %(count)s players in tier "%(tier)s" '
                    '(limit %(max)s). Adjust the swap or tier limits first.'
                ) % {
                    'team': auction.team_id.name,
                    'count': count,
                    'tier': tl.tier_id.name,
                    'max': tl.max_players,
                })

    def action_confirm_swap(self):
        self.ensure_one()
        if not self.source_line_id or not self.source_player_id:
            raise UserError(_('Source player is missing.'))
        if not self.target_team_id:
            raise UserError(_('Please select a target team.'))
        target_line = self.env['auction.auction.player'].browse(self.target_line_id or 0)
        if not target_line.exists() or not target_line.player_id:
            raise UserError(_('Please select a player from the target team to swap with.'))

        source_auction = self.source_line_id.auction_id
        target_auction = target_line.auction_id
        if not source_auction or not target_auction:
            raise UserError(_('Auction records for one of the teams could not be found.'))
        if target_auction.team_id != self.target_team_id:
            raise UserError(_('Selected player does not belong to the chosen target team.'))
        if source_auction.id == target_auction.id:
            raise UserError(_('Cannot swap players within the same team.'))
        if self.source_line_id.id == target_line.id:
            raise UserError(_('Cannot swap a player with themselves.'))

        x_points = int(self.source_swap_points or 0)
        y_points = int(self.target_swap_points or 0)
        if x_points < 0 or y_points < 0:
            raise UserError(_('Points cannot be negative.'))

        player_x = self.source_player_id
        player_y = target_line.player_id
        old_x_points = self.source_line_id.points or 0
        old_y_points = target_line.points or 0

        spent_a = sum(source_auction.player_ids.mapped('points')) - old_x_points + y_points
        if spent_a > (source_auction.total_point or 0):
            raise UserError(_(
                '"%(team)s" would exceed its budget after the swap '
                '(spent %(spent)s / budget %(budget)s).'
            ) % {
                'team': source_auction.team_id.name,
                'spent': spent_a,
                'budget': source_auction.total_point,
            })

        spent_b = sum(target_auction.player_ids.mapped('points')) - old_y_points + x_points
        if spent_b > (target_auction.total_point or 0):
            raise UserError(_(
                '"%(team)s" would exceed its budget after the swap '
                '(spent %(spent)s / budget %(budget)s).'
            ) % {
                'team': target_auction.team_id.name,
                'spent': spent_b,
                'budget': target_auction.total_point,
            })

        # Post-swap rosters for tier checks
        source_players_after = (
            (source_auction.player_ids - self.source_line_id).mapped('player_id') | player_y
        )
        target_players_after = (
            (target_auction.player_ids - target_line).mapped('player_id') | player_x
        )
        self._assert_tier_capacity(source_auction, source_players_after)
        self._assert_tier_capacity(target_auction, target_players_after)

        # Execute swap
        self.source_line_id.write({
            'auction_id': target_auction.id,
            'points': x_points,
        })
        target_line.write({
            'auction_id': source_auction.id,
            'points': y_points,
        })
        player_x.assigned_team_id = target_auction.team_id
        player_y.assigned_team_id = source_auction.team_id

        tournament = self.tournament_id
        fmt = (tournament.format_points if tournament
               else (lambda n: '{:,}'.format(int(n or 0))))
        msg_x = '%s swapped to %s for %s (from %s)' % (
            player_x.name, target_auction.team_id.name, fmt(x_points), source_auction.team_id.name)
        msg_y = '%s swapped to %s for %s (from %s)' % (
            player_y.name, source_auction.team_id.name, fmt(y_points), target_auction.team_id.name)
        player_x.create_auction_history(
            target_auction.team_id.id, msg_x,
            tournament_id=tournament.id if tournament else False, player=player_x)
        player_y.create_auction_history(
            source_auction.team_id.id, msg_y,
            tournament_id=tournament.id if tournament else False, player=player_y)

        notify = '%s ↔ %s swapped successfully.' % (player_x.name, player_y.name)
        self.env.user.notify_success(message=notify, title='Players Swapped')
        return {'type': 'ir.actions.act_window_close'}
