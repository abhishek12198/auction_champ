# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class SellPlayer(models.TransientModel):
    _name = 'auction.sell.player'

    final_point = fields.Integer(string="Selling for (Points)", required=True)
    team_id = fields.Many2one('auction.team', 'Sold To', required=True)
    team_name = fields.Char(related='team_id.name', string='Team Name')
    points_remaining = fields.Integer()
    players_remaining = fields.Integer()
    team_auction_id = fields.Many2one('auction.auction')
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo = fields.Binary(related='player_id.photo')
    team_logo = fields.Binary(related='team_id.logo')
    suggestion = fields.Html()

    @api.onchange('team_auction_id')
    def onchange_team_auction_id(self):
        suggestion_html = ""
        if self.team_auction_id.max_limited == 'yes':
            suggestion_html = f"""
                        <strong><p style="color: blue; text-align: right;">One player can go maximum points upto {self.team_auction_id.max_points}</p></strong>
                    """
        else:
            remaining_players = self.team_auction_id.remaining_players_count - 1
            base_point = self.team_auction_id.base_point
            max_points_for_next_player = self.team_auction_id.remaining_points - (remaining_players * base_point)
            if self.team_auction_id.remaining_players_count > 1:
                suggestion_html = f"""
                                <strong><p style="color: blue; text-align: right;">One player can go maximum points upto {max_points_for_next_player}</p></strong>
                                <strong><p style="color: blue; text-align: right;">Remaining players you can bid for base points  {base_point}</p></strong>
                            """
            else:
                suggestion_html = f"""
                                    <strong><p style="color: blue; text-align: right;">This player can go maximum points upto {max_points_for_next_player}</p></strong>
                                    """

        self.suggestion = suggestion_html

    @api.model
    def default_get(self, fields):
        defaults = super(SellPlayer, self).default_get(fields)
        if self.env.context.get('active_id', False):
            icon_players = self.env['auction.team'].search([]).mapped('key_player_ids')
            if icon_players:
                if self.env.context.get('active_id', False) in icon_players.ids:
                    player = self.env['auction.team.player'].browse(self.env.context.get('active_id', False))
                    message = player.name + ' is an icon player'
                    raise ValidationError(message)

            defaults.update({'player_id': self.env.context.get('active_id', False)})
        auction_base_value = list(set(self.env['auction.auction'].search([]).mapped('base_point')))
        if auction_base_value:
            defaults.update({'final_point': auction_base_value[0]})
        else:
            defaults.update({'final_point': 1000})
        return defaults

    @api.onchange('final_point', 'team_auction_id', 'team_id')
    def onchange_final_point(self):
        if not self.team_auction_id:
            return

        auction_base_point = self.team_auction_id.base_point
        auction_max_limited = self.team_auction_id.max_limited
        self_final_point = self.final_point

        if self_final_point < auction_base_point:
            self.final_point = auction_base_point
            message = 'The base point should not fall below ' + str(auction_base_point) + ' points'
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _(message)
                }
            }

        if auction_max_limited == 'yes':
            auction_max_point = self.team_auction_id.max_points
            if self_final_point > auction_max_point:
                self.final_point = auction_max_point
                message = 'The base point should not go beyond ' + str(auction_max_point) + ' points'
                return {
                    'warning': {
                        'title': _('Warning'),
                        'message': _(message)
                    }
                }

        players_remaining = self.players_remaining - 1
        points_remaining = self.points_remaining
        temp_number = players_remaining * auction_base_point
        print(points_remaining, temp_number)
        max_limit_player = points_remaining - temp_number
        if self_final_point > max_limit_player:
            self.final_point = max_limit_player
            message = 'Limit Exceeded! You can assign max points for this player up to ' + str(
                max_limit_player) + ' points!'
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _(message)
                }
            }

    @api.onchange('players_remaining')
    def onchange_players_remaining(self):
        domain = {'domain': {'team_id': [('id', 'in', [])]}}
        auctions = self.env['auction.auction'].search([('remaining_players_count', '>', 0)])
        if auctions:
            print(len(auctions))
            team_ids = auctions.mapped('team_id')
            domain = {'domain': {'team_id': [('id', 'in', team_ids.ids)]}}
        return domain

    @api.onchange('team_id')
    def onchange_team_id(self):
        if self.team_id:
            team_auction_record = self.env['auction.auction'].search([('team_id', '=', self.team_id.id)])
            if team_auction_record:
                if team_auction_record.remaining_points == 0 or team_auction_record.remaining_players_count == 0:
                    raise ValidationError("Team is full or the points are empty")
                self.team_auction_id = team_auction_record.id
                self.points_remaining = team_auction_record.remaining_points
                self.players_remaining = team_auction_record.remaining_players_count
            else:
                raise ValidationError("This team is not a part of the current Auction")
        else:
            self.team_auction_id = False
            self.points_remaining = 0
            self.players_remaining = 0

    def button_sell_player(self):
        player_id = self.env.context.get('active_id', False)
        if player_id:
            player = self.env['auction.team.player'].browse(player_id)
            auction = self.team_auction_id
            auction_line_data = {
                'player_id': player.id,
                'points': self.final_point,

            }
            message = player.name + ' sold to the '+ auction.team_id.name + ' for ' +str(self.final_point) + ' points successfully!'
            auction.player_ids = [(0, 0, auction_line_data)]
            player.assigned_team_id = auction.team_id and auction.team_id.id or False
            player.state = 'sold'
            player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)
            self.env.user.notify_success(message)


