# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class StartAuction(models.TransientModel):
    _name = 'auction.start.auction'

    max_points = fields.Integer(string='Max Points')
    max_players = fields.Integer(string='Max no of players')
    base_point = fields.Integer(string="Base point for a player", default=1000)
    team_ids = fields.Many2many('auction.team', 'start_auction_team_rel', 'auction_start_id', 'team_id', 'Teams')
    max_limited = fields.Selection([('yes', 'Yes'), ('no', 'No')], default='no')
    max_point_player = fields.Integer('Max Point for a player')
    auction_bid_slab_ids = fields.One2many('auction.bid.slab', 'wizard_id', 'Slab')

    @api.onchange('max_limited')
    def onchange_max_limited(self):
        if self.max_limited == 'no':
            self.max_points = 0

    @api.onchange('base_point')
    def onchange_base_point(self):
        if self.base_point <= 0:
            self.base_point = 1000

    def button_start_auction(self):
        auction_obj = self.env['auction.auction']
        auction_list = []
        if self.max_points <= 0:
            raise ValidationError("Points cannot be 0")
        if self.max_players <= 0:
            raise ValidationError("Number of players cannot be 0")

        if not len(self.team_ids) >= 2:
            raise ValidationError("Select atleast two teams")
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        bid_slab_data = [(0, 0, {'from_amount': line.from_amount, 'to_amount': line.to_amount,'increment': line.increment}) for line in self.auction_bid_slab_ids]
        if self.team_ids:
            existing_auctions  = auction_obj.search([('team_id', 'in', self.team_ids.ids)])
            if existing_auctions:
                raise ValidationError("Auction rules has been created already for the teams. Please delete the auction records and continue creating.")
            for team in self.team_ids:
                auction_data = {
                    'team_id': team.id,
                    'total_point': self.max_points,
                    'max_players': self.max_players,
                    'base_point': self.base_point,
                    'max_limited': self.max_limited,
                    'max_points': self.max_point_player,
                    'auction_bid_slab_ids': bid_slab_data,
                }

                auction_data.update({'tournament_id': tournament_id.id})
                auction_list.append(auction_data)

        if auction_list:
            auction_obj.create(auction_list)
        self.env.user.notify_success('Auction process initiated successfully for the selected teams!')
        return {
            'name': _('Players in Auction'),
            'view_mode': 'tree,form',
            'domain': [('state', '=', 'auction')],
            'res_model': 'auction.team.player',
            'type': 'ir.actions.act_window',
            'context': {'create': False},
        }

class AuctionBidSlab(models.TransientModel):

    _name = 'auction.bid.slab'

    wizard_id = fields.Many2one('auction.start.auction', ondelete='cascade')

    from_amount = fields.Integer(required=True)
    to_amount = fields.Integer(required=True)
    increment = fields.Integer(required=True)