# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class Auction(models.Model):

    _name = 'auction.auction'
    _rec_name = 'team_id'
    _order = 'remaining_players_count,id'
    team_id = fields.Many2one('auction.team', 'Team')
    team_logo = fields.Binary(related='team_id.logo')
    manager = fields.Char(related='team_id.manager', string="Owner")
    player_ids = fields.One2many('auction.auction.player', 'auction_id', 'Players')
    total_point = fields.Integer(string="Total points")
    active = fields.Boolean(default=True)
    max_players = fields.Integer(string='Max no of players')
    base_point = fields.Integer(string='Base Point')
    max_limited = fields.Selection([('yes', 'Yes'), ('no', 'No')], default='no')
    max_points = fields.Integer('Max Points')
    remaining_points = fields.Integer(compute='_calculate_remaining_points', string="Remaining points")
    remaining_players_count = fields.Integer(compute='_calculate_remaining_players_count', store=True, string="Remaining players required")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    max_call = fields.Integer(compute='_calculate_max_call', string="Max Call")
    auction_bid_slab_ids = fields.One2many('auction.auction.bid.slab', 'auction_id', 'Slab')
    tier_limit_ids = fields.One2many('auction.auction.tier.limit', 'auction_id', 'Tier Limits')


    @api.depends('player_ids', 'player_ids.points')
    def _calculate_remaining_points(self):
        for record in self:
            points_from_players = 0
            if record.player_ids:
                points_from_players = sum([line.points for line in record.player_ids])
            record.remaining_points = record.total_point - points_from_players

    @api.depends('player_ids')
    def _calculate_remaining_players_count(self):
        for record in self:
            players_recruited = 0
            if record.player_ids:
                players_recruited = len(record.player_ids)
            record.remaining_players_count = record.max_players - players_recruited

    @api.depends(
        'player_ids',
        'player_ids.points',
        'total_point',
        'max_players',
        'base_point',
        'auction_bid_slab_ids',
        'tier_limit_ids',
        'tier_limit_ids.max_call',
        'tier_limit_ids.base_point',
        'tier_limit_ids.max_players',
    )
    def _calculate_max_call(self):
        on_stage = self.env['auction.team.player'].search(
            [('is_on_stage', '=', True)], limit=1
        )
        player = on_stage if on_stage else None
        for record in self:
            record.max_call = record.get_max_bid_for_team(record, player)

    def _get_budget_safe_max(self, team, player=None):
        # Compute directly from stored fields — never read non-stored computed fields
        # inside another computed field to avoid ORM cache re-entrancy issues.
        points_used = sum(p.points for p in team.player_ids) if team.player_ids else 0
        remaining_points = team.total_point - points_used
        remaining_players = team.max_players - len(team.player_ids)

        if remaining_players <= 0:
            return 0

        if not player or not player.tier_id or not team.tier_limit_ids:
            # Fallback: use global base_point uniformly across all remaining slots
            base = team.base_point or 0
            safe_max = remaining_points - ((remaining_players - 1) * base)
            return max(safe_max, 0)

        # Per-tier reserve: each tier's remaining slots × that tier's min bid
        reserve = 0
        tier_slots_accounted = 0
        player_tier_id = player.tier_id.id

        for tl in team.tier_limit_ids:
            recruited = self.env['auction.auction.player'].search_count([
                ('auction_id', '=', team.id),
                ('player_id.tier_id', '=', tl.tier_id.id),
            ])
            remaining_slots = max(tl.max_players - recruited, 0)
            if tl.tier_id.id == player_tier_id:
                # The current slot is being filled — exclude it from the reserve
                remaining_slots = max(remaining_slots - 1, 0)
            tier_min_bid = tl.base_point if tl.base_point > 0 else (team.base_point or 0)
            reserve += remaining_slots * tier_min_bid
            tier_slots_accounted += remaining_slots

        # Players not covered by any tier limit fall back to global base_point
        uncovered = max((remaining_players - 1) - tier_slots_accounted, 0)
        reserve += uncovered * (team.base_point or 0)

        safe_max = remaining_points - reserve
        return max(safe_max, 0)

    def _get_rule_cap(self, safe_max, player=None):
        if player and player.tier_id and self.tier_limit_ids:
            tl = self.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tl and tl[0].max_call > 0:
                return min(tl[0].max_call, safe_max)
        return safe_max

    def _snap_to_slab(self, amount):
        """
        Adjust amount DOWN to the nearest valid slab step
        """
        for slab in self.auction_bid_slab_ids.sorted('from_amount', reverse=True):
            if amount >= slab.from_amount:
                base = slab.from_amount
                inc = slab.increment

                snapped = base + ((amount - base) // inc) * inc
                return min(snapped, amount)

        return amount

    def get_max_bid_for_team(self, team, player=None):
        self.ensure_one()

        # 1️⃣ Per-tier budget safety (reserves each tier's remaining slots at their min bid)
        safe_max = self._get_budget_safe_max(team, player)

        # 2️⃣ Tier-level per-player cap (0 = unlimited)
        rule_cap = self._get_rule_cap(safe_max, player)

        # 3️⃣ Slab snapping
        return self._snap_to_slab(rule_cap)


class AuctionPlayer(models.Model):

    _name = 'auction.auction.player'

    auction_id = fields.Many2one('auction.auction', 'Auction', ondelete='cascade')
    player_id = fields.Many2one('auction.team.player', 'Player')
    contact    = fields.Char(related='player_id.contact',      string='Contact')
    role       = fields.Char(related='player_id.role',         string='Role')
    tier_id    = fields.Many2one(related='player_id.tier_id',  string='Tier', comodel_name='auction.player.tier')
    icon_player = fields.Boolean(related='player_id.icon_player',   string='Key Player')
    points = fields.Integer(string='Sold For (pts)')
    # Fields used by the signed-players kanban card
    tier_color = fields.Char(string='Tier Color', compute='_compute_tier_color')

    def _compute_tier_color(self):
        for rec in self:
            rec.tier_color = rec.player_id.tier_id.color or '#3498db'

    def action_recall_to_auction(self):
        context = self.env.context.copy()
        for player in self:
            player_obj = player.player_id
            player.player_id.assigned_team_id = False
            player.player_id.state = 'auction'

            player.unlink()
            if not context.get('mass_update', False):
                message = player_obj.name + ' brought back to auction successfully!. The player will be available in the auction'
                self.env.user.notify_success(message)

class AuctionBidSlab(models.Model):

    _name = 'auction.auction.bid.slab'

    auction_id = fields.Many2one('auction.auction', ondelete='cascade')
    from_amount = fields.Integer(required=True)
    to_amount = fields.Integer(required=True)
    increment = fields.Integer(required=True)


class AuctionAuctionTierLimit(models.Model):
    _name = 'auction.auction.tier.limit'
    _description = 'Auction Team Tier Limit'

    auction_id = fields.Many2one('auction.auction', ondelete='cascade')
    tier_id = fields.Many2one('auction.player.tier', string='Tier', required=True)
    max_players = fields.Integer(string='Max Players', required=True, default=1)
    base_point = fields.Integer(string='Base Point', default=0,
        help="Minimum bid for a player of this tier. Leave 0 to use the global base point.")
    max_call = fields.Integer(string='Max Call for a Player', default=0,
        help="Maximum bid allowed for a single player of this tier. Leave 0 for no cap.")