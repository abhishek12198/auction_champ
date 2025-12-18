# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class BringUnsoldPlayers(models.TransientModel):
    _name = 'auction.bring.unsold.players'

    player_ids = fields.Many2many('auction.team.player', 'player_unsold_player_rel', 'unsold_player_id', 'player_id', 'Selected Players')
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')

    @api.model
    def default_get(self, fields):
        players = self.env['auction.team.player'].browse(self.env.context.get('active_ids', []))
        if any(player.state != "unsold" for player in players):
            raise ValidationError("Only the players in Unsold status can be brought back to Auction! "
                                  "Please unselect the players which are not in Unsold status!")
        defaults = super(BringUnsoldPlayers, self).default_get(fields)
        if self.env.context.get('active_ids', []):
            defaults.update({'player_ids': [(6, 0, self.env.context.get('active_ids', []))]})
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            defaults.update({'tournament_id': tournament_id.id})
        return defaults

    def button_set_to_auction(self):
        players = self.player_ids
        players.with_context({'mass_update' : True}).action_auction()



