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
    max_call = fields.Integer(compute='_calculate_max_call', store=True, string="Max Call")
    auction_bid_slab_ids = fields.One2many('auction.auction.bid.slab', 'auction_id', 'Slab')


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
        'remaining_players_count',
        'max_players',
        'max_limited',
        'remaining_points',
        'base_point',
        'auction_bid_slab_ids'
    )
    def _calculate_max_call(self):
        for record in self:
            record.max_call = record.get_max_bid_for_team(record)

    # @api.depends('player_ids', 'remaining_players_count','max_players', 'max_limited')
    # def _calculate_max_call(self):
    #     for record in self:
    #         max_call = record.get_max_bid_for_team(record)
    #         record.max_call = max_call
    #         # if record.max_players == record.remaining_players_count:
    #         #     rem_player_count = record.remaining_players_count - 1
    #         #     record.max_call = record.total_point - (rem_player_count * record.base_point)
    #         # elif record.max_players != record.remaining_players_count:
    #         #     rem_player_count = record.remaining_players_count - 1
    #
    #         #     record.max_call = record.remaining_points - (rem_player_count * record.base_point)

    def _get_budget_safe_max(self, team):
        remaining_points = team.remaining_points
        remaining_players = team.remaining_players_count
        base = team.base_point  # IMPORTANT: use team, not self

        if remaining_players <= 0:
            return 0

        safe_max = remaining_points - ((remaining_players - 1) * base)
        return max(safe_max, 0)

    def _get_rule_cap(self, safe_max):
        if self.max_limited == 'yes':
            return min(self.max_points, safe_max)
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

    def get_max_bid_for_team(self, team):
        self.ensure_one()

        # 1️⃣ Budget safety
        safe_max = self._get_budget_safe_max(team)

        # 2️⃣ Auction rule cap
        rule_cap = self._get_rule_cap(safe_max)

        # 3️⃣ Slab snapping
        return self._snap_to_slab(rule_cap)


class AuctionPlayer(models.Model):

    _name = 'auction.auction.player'

    auction_id = fields.Many2one('auction.auction', 'Auction', ondelete='cascade',)
    player_id = fields.Many2one('auction.team.player', 'Player')
    contact = fields.Char(related='player_id.contact', string='Contact')
    points = fields.Integer(string='Points')

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