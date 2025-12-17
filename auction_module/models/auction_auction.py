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

    @api.depends('player_ids', 'remaining_players_count','max_players')
    def _calculate_max_call(self):
        for record in self:
            if record.max_players == record.remaining_players_count:
                rem_player_count = record.remaining_players_count - 1
                record.max_call = record.total_point - (rem_player_count * record.base_point)
            elif record.max_players != record.remaining_players_count:
                rem_player_count = record.remaining_players_count - 1
                record.max_call = record.remaining_points - (rem_player_count * record.base_point)

class AuctionPlayer(models.Model):

    _name = 'auction.auction.player'

    auction_id = fields.Many2one('auction.auction', 'Auction', ondelete='cascade',)
    player_id = fields.Many2one('auction.team.player', 'Player')
    contact = fields.Char(related='player_id.contact', string='Contact')
    points = fields.Integer(string='Points')

    def action_recall_to_auction(self):
        for player in self:
            player_obj = player.player_id
            player.player_id.assigned_team_id = False
            player.player_id.state = 'auction'

            player.unlink()
            message = player_obj.name + ' brought back to auction successfully!. The player will be available in the auction'
            self.env.user.notify_success(message)

