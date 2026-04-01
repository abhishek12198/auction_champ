# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class SetPlayerDraft(models.TransientModel):
    _name = 'auction.player.draft'

    player_ids = fields.Many2many('auction.team.player', 'player_draft_player_rel', 'auction_player_id', 'player_id', 'Selected Players')
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')

    @api.model
    def default_get(self, fields):
        defaults = super(SetPlayerDraft, self).default_get(fields)
        players = self.env['auction.team.player'].browse(self.env.context.get('active_ids', []))
        if any(player.state not in ["auction"] for player in players):
            raise ValidationError("Only the players in In Auction status can be reset to Draft! "
                                  "Please unselect the players which are not in In Auction status!")
        if self.env.context.get('active_ids', []):
            defaults.update({'player_ids': [(6, 0, self.env.context.get('active_ids', []))]})
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            defaults.update({'tournament_id': tournament_id.id})
        return defaults

    def button_set_to_draft(self):
        players = self.player_ids
        if any(player.state != "auction" for player in players):
            raise ValidationError("Only the players in In Auction status can be reset to Draft! "
                                  "Please unselect the players which are not in In Auction status!")
        players.write({'state': 'draft'})
        message = 'Selected Players are reset to Draft!'
        self.env.user.notify_success(message)



