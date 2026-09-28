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

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html_escape


class SellPlayer(models.TransientModel):
    _name = 'auction.sell.player'
    _description = 'Sell Player'

    final_point = fields.Integer(string="Selling for (Points)", required=True)
    team_id = fields.Many2one('auction.team', 'Sold To', required=True)
    team_selection = fields.Selection(selection='_get_team_selection', string='Select Team')
    team_name = fields.Char(related='team_id.name', string='Team Name')
    points_remaining = fields.Integer(string='Purse Left')
    players_remaining = fields.Integer(string='Slots Left')
    max_bid = fields.Integer(string='Max Bid', readonly=True)
    effective_base = fields.Integer(string='Base', readonly=True)
    points_hint = fields.Char(string='Points Hint', readonly=True)
    point_unit_label = fields.Char(string='Unit', readonly=True, default='PTS')
    preset_html = fields.Html(string='Quick Points', sanitize=False)
    team_auction_id = fields.Many2one('auction.auction')
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo = fields.Binary(related='player_id.photo')
    # Kept for compatibility; view uses team_logo_html (URL) for speed.
    team_logo = fields.Binary(related='team_id.logo')
    team_logo_html = fields.Html(string='Team Logo', sanitize=False)
    tier_summary_html = fields.Html(string='Tier Slots', sanitize=False)
    suggestion = fields.Html()

    def _get_active_player(self):
        """Player being sold — from wizard field or action context."""
        if self.player_id:
            return self.player_id
        active_id = self.env.context.get('active_id')
        if active_id:
            return self.env['auction.team.player'].browse(active_id)
        return self.env['auction.team.player']

    def _get_point_unit_label(self, player=None):
        player = player or self._get_active_player()
        if player and player.tournament_id:
            unit = player.tournament_id.get_point_unit()
            if unit:
                return unit.symbol or unit.name or 'PTS'
        return 'PTS'

    def _tournament_auctions(self, player=None):
        """Auction rule rows for the player's tournament only."""
        player = player or self._get_active_player()
        Auction = self.env['auction.auction']
        if not player or not player.tournament_id:
            return Auction.browse()
        return Auction.search([
            ('tournament_id', '=', player.tournament_id.id),
        ])

    def _get_team_selection(self):
        player = self._get_active_player()
        auctions = self._tournament_auctions(player)
        if not auctions:
            return []
        auctions.mapped('team_id')
        choices = []
        for auction in auctions.sorted(key=lambda a: (a.team_id.name or '').lower()):
            team = auction.team_id
            if not team:
                continue
            purse = int(auction.remaining_points or 0)
            label = '%s · %s left' % (team.name, '{:,}'.format(purse))
            choices.append((str(team.id), label))
        return choices

    def _format_points_hint(self, base, max_bid, unit_label=None):
        unit = unit_label or self.point_unit_label or 'PTS'
        return 'Base %s  ·  Max %s  ·  %s' % (
            '{:,}'.format(int(base or 0)),
            '{:,}'.format(int(max_bid or 0)),
            unit,
        )

    def _get_bid_slabs(self, auction, player=None):
        """Return sorted slab dicts for increment lookups (auction, else tournament splits)."""
        slabs = []
        if auction and auction.auction_bid_slab_ids:
            for s in auction.auction_bid_slab_ids.sorted('from_amount'):
                slabs.append({
                    'from_amount': int(s.from_amount or 0),
                    'to_amount': int(s.to_amount or 0) or 10 ** 12,
                    'increment': int(s.increment or 0) or 1,
                })
            return slabs

        player = player or self._get_active_player()
        tournament = player.tournament_id if player else False
        if tournament and tournament.points_split_ids:
            splits = list(tournament.points_split_ids.sorted('points'))
            for i, split in enumerate(splits):
                to_amt = (splits[i + 1].points - 1) if i + 1 < len(splits) else 10 ** 12
                slabs.append({
                    'from_amount': int(split.points or 0),
                    'to_amount': int(to_amt),
                    'increment': int(split.no_of_calls or 0) or 1,
                })
        return slabs

    def _slab_increment_at(self, amount, slabs):
        if not slabs:
            return 50
        amount = int(amount or 0)
        for slab in slabs:
            if amount >= slab['from_amount'] and amount < slab['to_amount']:
                return max(int(slab['increment'] or 1), 1)
        return max(int(slabs[-1]['increment'] or 1), 1)

    def _snap_amount_to_slabs(self, amount, auction, base, max_bid, slabs):
        """Snap to a valid bid using auction slab rules, clamped to [base, max_bid]."""
        amount = int(amount or 0)
        base = int(base or 0)
        max_bid = int(max_bid or 0)
        if amount <= base:
            return base
        if amount >= max_bid:
            return max_bid
        if auction:
            snapped = int(auction._snap_to_slab(amount) or amount)
        else:
            # Manual snap-down using slab list
            snapped = amount
            for slab in sorted(slabs, key=lambda s: s['from_amount'], reverse=True):
                if amount < slab['from_amount']:
                    continue
                slab_base = slab['from_amount']
                inc = max(int(slab['increment'] or 1), 1)
                snapped = slab_base + ((amount - slab_base) // inc) * inc
                snapped = min(snapped, amount, slab['to_amount'])
                break
        if snapped < base:
            snapped = base
        if snapped > max_bid:
            snapped = max_bid
        return snapped

    def _build_proportional_chip_values(self, auction, player, base, max_bid, count=7):
        """Up to ``count`` slab-valid bids evenly spaced from base → max (Safe)."""
        base = int(base or 0)
        max_bid = int(max_bid or 0)
        if max_bid < base:
            max_bid = base
        if base == max_bid:
            return [base]

        slabs = self._get_bid_slabs(auction, player)
        count = max(2, min(int(count or 7), 7))

        # Evenly spaced targets across the purse range, then snap to slabs.
        targets = []
        for i in range(count):
            if count == 1:
                raw = base
            else:
                raw = base + int(round((max_bid - base) * float(i) / float(count - 1)))
            targets.append(raw)

        values = []
        seen = set()
        for i, raw in enumerate(targets):
            if i == 0:
                snapped = base
            elif i == len(targets) - 1:
                snapped = max_bid
            else:
                snapped = self._snap_amount_to_slabs(raw, auction, base, max_bid, slabs)
                # Prefer moving toward max if snap collapsed onto previous chip
                if snapped in seen and slabs:
                    inc = self._slab_increment_at(snapped, slabs)
                    candidate = snapped + inc
                    while candidate <= max_bid and candidate in seen:
                        candidate += self._slab_increment_at(candidate, slabs)
                    if candidate <= max_bid and candidate not in seen:
                        snapped = candidate
            if snapped in seen:
                continue
            seen.add(snapped)
            values.append(snapped)

        # Guarantee endpoints
        if values[0] != base:
            values.insert(0, base)
        if values[-1] != max_bid:
            values.append(max_bid)

        # Deduplicate / trim to at most 7 while keeping first & last
        unique = []
        for v in values:
            if v not in unique:
                unique.append(v)
        if len(unique) <= 7:
            return unique
        # Keep endpoints + evenly pick from middle
        middle = unique[1:-1]
        need = 5  # 7 total with endpoints
        if len(middle) <= need:
            return [unique[0]] + middle + [unique[-1]]
        picked = []
        for i in range(need):
            idx = int(round(i * (len(middle) - 1) / float(need - 1))) if need > 1 else 0
            if middle[idx] not in picked:
                picked.append(middle[idx])
        return [unique[0]] + picked[:need] + [unique[-1]]

    def _build_preset_html(self, auction, player, base, max_bid, unit_label=None):
        """Quick-select chips: up to 7 slab-snapped bids from Base → Safe (max)."""
        base = int(base or 0)
        max_bid = int(max_bid or 0)
        unit = unit_label or self.point_unit_label or 'PTS'
        if max_bid < base:
            max_bid = base

        values = self._build_proportional_chip_values(
            auction, player, base, max_bid, count=7)

        chips = []
        for idx, value in enumerate(values):
            if idx == 0:
                label, kind = 'Base', 'base'
            elif idx == len(values) - 1 and value == max_bid and max_bid > base:
                label, kind = 'Safe', 'safe'
            else:
                label, kind = 'Bid', 'preset'
            cls = 'asp-preset-btn'
            if kind == 'safe':
                cls += ' asp-preset-safe'
            elif kind == 'base':
                cls += ' asp-preset-base'
            chips.append(
                '<button type="button" class="%s" data-points="%d">'
                '<span class="asp-preset-label">%s</span>'
                '<span class="asp-preset-val">%s</span>'
                '</button>' % (
                    cls,
                    int(value),
                    html_escape(label),
                    html_escape('{:,}'.format(int(value))),
                )
            )

        if not chips:
            return ''
        return (
            '<div class="asp-presets" data-unit="%s">%s</div>'
            % (html_escape(unit), ''.join(chips))
        )

    def _build_team_logo_html(self, team):
        if not team:
            return ''
        if team.logo:
            src = '/web/image/auction.team/%d/logo' % team.id
            return (
                '<img class="asp-team-logo-img" src="%s" alt="%s"/>'
                % (src, html_escape(team.name or 'Team'))
            )
        initials = (team.name or '?')[:1].upper()
        return (
            '<div class="asp-team-logo-ph" aria-hidden="true">%s</div>'
            % html_escape(initials)
        )

    def _build_tier_summary_html(self, auction, player):
        if not auction or not auction.tier_limit_ids:
            return (
                '<div class="asp-tier-empty">No tier limits configured for this team.</div>'
            )

        domain = [('auction_id', '=', auction.id)]
        if player:
            domain.append(('player_id', '!=', player.id))
        sold_by_tier = {}
        lines = self.env['auction.auction.player'].search(domain)
        for line in lines:
            tid = line.player_id.tier_id.id if line.player_id and line.player_id.tier_id else False
            if tid:
                sold_by_tier[tid] = sold_by_tier.get(tid, 0) + 1

        rows = []
        limits = auction.tier_limit_ids.sorted(
            key=lambda r: (
                r.tier_id.sequence if r.tier_id else 999,
                r.tier_id.name or '',
            )
        )
        for tl in limits:
            tier = tl.tier_id
            if not tier:
                continue
            sold = int(sold_by_tier.get(tier.id, 0))
            max_p = int(tl.max_players or 0)
            left = max(0, max_p - sold)
            color = tier.color or '#64748b'
            is_current = bool(player and player.tier_id and player.tier_id.id == tier.id)
            row_cls = 'asp-tier-row asp-tier-current' if is_current else 'asp-tier-row'
            rows.append(
                '<tr class="%s">'
                '<td><span class="asp-tier-dot" style="background:%s"></span>%s%s</td>'
                '<td class="asp-tier-num">%d / %d</td>'
                '<td class="asp-tier-num">%d</td>'
                '</tr>' % (
                    row_cls,
                    html_escape(color),
                    html_escape(tier.name or ''),
                    ' <span class="asp-tier-you">this player</span>' if is_current else '',
                    sold, max_p, left,
                )
            )

        return (
            '<table class="asp-tier-table">'
            '<thead><tr><th>Tier</th><th>Sold / Max</th><th>Left</th></tr></thead>'
            '<tbody>%s</tbody></table>'
            % ''.join(rows)
        )

    def _clear_team_stats(self):
        self.team_auction_id = False
        self.points_remaining = 0
        self.players_remaining = 0
        self.max_bid = 0
        self.effective_base = 0
        self.points_hint = False
        self.preset_html = False
        self.team_logo_html = False
        self.tier_summary_html = False
        self.suggestion = False

    @api.onchange('team_selection')
    def onchange_team_selection(self):
        if self.team_selection:
            self.team_id = int(self.team_selection)
            self.onchange_team_id()
        else:
            self.team_id = False
            self._clear_team_stats()

    @api.model
    def _get_effective_base_point(self, auction, player):
        """Return tier-specific base_point if configured (> 0), else fall back to the global base_point."""
        if player and player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(
                lambda l: l.tier_id.id == player.tier_id.id
            )
            if tier_limit and tier_limit[0].base_point > 0:
                return tier_limit[0].base_point
        return auction.base_point

    @api.onchange('team_auction_id')
    def onchange_team_auction_id(self):
        if not self.team_auction_id:
            self.suggestion = False
            return
        player = self._get_active_player()
        effective_base = self._get_effective_base_point(self.team_auction_id, player)
        tier_aware_max_call = self.team_auction_id.get_max_bid_for_team(self.team_auction_id, player)
        remaining_players = self.team_auction_id.remaining_players_count - 1
        if self.team_auction_id.remaining_players_count > 1:
            suggestion_html = (
                '<p>One player can go maximum up to <strong>%s</strong>.</p>'
                '<p>Remaining <strong>%d</strong> player(s) reserved at base <strong>%s</strong>.</p>'
            ) % (
                '{:,}'.format(int(tier_aware_max_call or 0)),
                remaining_players,
                '{:,}'.format(int(effective_base or 0)),
            )
        else:
            suggestion_html = (
                '<p>This player can go maximum up to <strong>%s</strong>.</p>'
            ) % '{:,}'.format(int(tier_aware_max_call or 0))
        self.suggestion = suggestion_html

    @api.model
    def default_get(self, fields_list):
        defaults = super(SellPlayer, self).default_get(fields_list)
        active_id = self.env.context.get('active_id', False)
        player = self.env['auction.team.player'].browse(active_id) if active_id else False

        if player:
            if player.tournament_id:
                icon_players = self.env['auction.team'].search([
                    ('tournament_id', '=', player.tournament_id.id),
                ]).mapped('key_player_ids')
            else:
                icon_players = self.env['auction.team.player']
            if player.id in icon_players.ids:
                raise ValidationError(_('%s is an icon player') % player.name)

            defaults['player_id'] = player.id
            unit_label = self._get_point_unit_label(player)
            defaults['point_unit_label'] = unit_label

            auctions = self._tournament_auctions(player)
            initial_base = 1000
            if auctions:
                initial_base = self._get_effective_base_point(auctions[0], player)
            defaults['final_point'] = initial_base
            defaults['effective_base'] = initial_base
            defaults['points_hint'] = self._format_points_hint(initial_base, 0, unit_label)
        return defaults

    @api.onchange('final_point', 'team_auction_id', 'team_id')
    def onchange_final_point(self):
        # Points are only editable after a team is selected
        if not self.team_id or not self.team_auction_id:
            return

        player = self._get_active_player()
        auction_base_point = self._get_effective_base_point(self.team_auction_id, player)
        self_final_point = self.final_point

        if self_final_point < auction_base_point:
            self.final_point = auction_base_point
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _('The base point should not fall below %s points') % auction_base_point,
                }
            }

        tier_aware_max_call = self.team_auction_id.get_max_bid_for_team(self.team_auction_id, player)
        if self_final_point > tier_aware_max_call:
            self.final_point = tier_aware_max_call
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _(
                        'Bid exceeds the max call of %s pts for this player tier'
                    ) % tier_aware_max_call,
                }
            }

        players_remaining = self.players_remaining - 1
        points_remaining = self.points_remaining
        global_base_point = self.team_auction_id.base_point
        temp_number = players_remaining * global_base_point
        max_limit_player = points_remaining - temp_number
        if self_final_point > max_limit_player:
            self.final_point = max_limit_player
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _(
                        'Limit Exceeded! You can assign max points for this player up to %s points!'
                    ) % max_limit_player,
                }
            }

    @api.onchange('players_remaining')
    def onchange_players_remaining(self):
        player = self._get_active_player()
        auctions = self._tournament_auctions(player)
        team_ids = auctions.mapped('team_id').ids if auctions else []
        return {'domain': {'team_id': [('id', 'in', team_ids)]}}

    @api.onchange('team_id')
    def onchange_team_id(self):
        if not self.team_id:
            self._clear_team_stats()
            return

        player = self._get_active_player()
        domain = [('team_id', '=', self.team_id.id)]
        if player and player.tournament_id:
            domain.append(('tournament_id', '=', player.tournament_id.id))
        team_auction_record = self.env['auction.auction'].search(domain, limit=1)

        if not team_auction_record:
            raise ValidationError(_("This team is not part of the player's tournament auction"))

        if team_auction_record.remaining_points == 0:
            raise ValidationError(_("Team is full or the points are empty"))

        team_auction_record.mapped('tier_limit_ids.tier_id')

        self.team_auction_id = team_auction_record.id
        self.points_remaining = team_auction_record.remaining_points
        self.players_remaining = team_auction_record.remaining_players_count

        effective_base = self._get_effective_base_point(team_auction_record, player)
        max_bid = team_auction_record.get_max_bid_for_team(team_auction_record, player)
        unit_label = self._get_point_unit_label(player)
        self.point_unit_label = unit_label
        self.effective_base = effective_base
        self.max_bid = max_bid
        self.points_hint = self._format_points_hint(effective_base, max_bid, unit_label)
        self.team_logo_html = self._build_team_logo_html(self.team_id)
        self.tier_summary_html = self._build_tier_summary_html(team_auction_record, player)
        self.preset_html = self._build_preset_html(
            team_auction_record, player, effective_base, max_bid, unit_label)

        if not self.final_point or self.final_point < effective_base:
            self.final_point = effective_base
        elif self.final_point > max_bid:
            self.final_point = max_bid

        if player and player.tier_id and team_auction_record.tier_limit_ids:
            tier_limit = team_auction_record.tier_limit_ids.filtered(
                lambda l: l.tier_id.id == player.tier_id.id
            )
            if tier_limit:
                already_sold = self.env['auction.auction.player'].search_count([
                    ('auction_id', '=', team_auction_record.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                    ('player_id', '!=', player.id),
                ])
                remaining_slots = tier_limit[0].max_players - already_sold
                if remaining_slots <= 0:
                    raise ValidationError(
                        _("This team has already reached the maximum limit of %d player(s) "
                          "allowed from the '%s' tier.") % (
                            tier_limit[0].max_players, player.tier_id.name)
                    )

        self.onchange_team_auction_id()

    def button_sell_player(self):
        player_id = self.env.context.get('active_id', False)
        if player_id:
            player = self.env['auction.team.player'].browse(player_id)
            auction = self.team_auction_id

            # Hard check: purse must cover the tier's minimum bid
            if player.tier_id and auction.tier_limit_ids:
                tier_limit_base = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                _tier_min = (tier_limit_base[0].base_point
                             if tier_limit_base and tier_limit_base[0].base_point > 0
                             else (auction.base_point or 0))
                if _tier_min > 0 and auction.remaining_points < _tier_min:
                    raise UserError(
                        "Cannot sell '%s' to %s — the team's remaining purse (%d pts) is "
                        "below the minimum required for the '%s' tier (%d pts)." % (
                            player.name,
                            auction.team_id.name,
                            auction.remaining_points,
                            player.tier_id.name,
                            _tier_min,
                        )
                    )

            # Hard check: final_point must not exceed the tier-aware max call
            tier_aware_max_call = auction.get_max_bid_for_team(auction, player)
            if self.final_point > tier_aware_max_call:
                raise UserError(
                    "Cannot sell '%s' to %s for %d pts — the maximum allowed call "
                    "for this team is %d pts." % (
                        player.name,
                        auction.team_id.name,
                        self.final_point,
                        tier_aware_max_call,
                    )
                )

            # Tier limit hard check
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit:
                    already_sold = self.env['auction.auction.player'].search_count([
                        ('auction_id', '=', auction.id),
                        ('player_id.tier_id', '=', player.tier_id.id),
                    ])
                    if already_sold >= tier_limit[0].max_players:
                        raise UserError(
                            "Cannot sell '%s' to %s — the team has already reached the "
                            "maximum limit of %d player(s) from the '%s' tier." % (
                                player.name,
                                auction.team_id.name,
                                tier_limit[0].max_players,
                                player.tier_id.name,
                            )
                        )
            auction_line_data = {
                'player_id': player.id,
                'points': self.final_point,

            }
            sold_amt = player._history_value(self.final_point)
            message = '%s sold to %s for %s!' % (player.name, auction.team_id.name, sold_amt)
            if player.tier_id and player.tier_id.mystery:
                message = '%s sold to %s for %s!' % ('???', auction.team_id.name, sold_amt)
                player.mystery_revealed = False
            auction_player_line = self.env['auction.auction.player'].search([('player_id', '=', player.id)])
            if not auction_player_line:
                auction.player_ids = [(0, 0, auction_line_data)]
                player.assigned_team_id = auction.team_id and auction.team_id.id or False
                player.state = 'sold'
                player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)
            else:
                auction_line_data.update({'auction_id': auction.id})
                auction_player_line.write(auction_line_data)
            notify_msg = '%s sold to %s for %s!' % (
                player.name, auction.team_id.name, player._history_value(self.final_point)
            )
            self.env.user.notify_success(
                message=notify_msg,
                title="CONGRATULATIONS!"
            )

            return {'type': 'ir.actions.act_window_close'}

        return {'type': 'ir.actions.act_window_close'}
