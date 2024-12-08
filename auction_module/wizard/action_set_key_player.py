# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class SetKeyPlayer(models.TransientModel):
    _name = 'auction.set.key.player'


    team_id = fields.Many2one('auction.team', 'Team', required=True)
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo  = fields.Binary()
    team_logo = fields.Binary()

    @api.model
    def default_get(self, fields):
        defaults = super(SetKeyPlayer, self).default_get(fields)
        if self.env.context.get('active_id', False):
            player = self.env['auction.team.player'].browse(self.env.context.get('active_id', False))
            defaults.update({'player_photo': player.photo,'player_id': self.env.context.get('active_id', False)})
        return defaults

    @api.onchange('team_id')
    def onchange_team(self):
        if self.team_id:
            self.team_logo = self.team_id.logo
        else:
            self.team_logo = False

    def button_set_keyplayer(self):
        player_id = self.env.context.get('active_id', False)
        if player_id:
            player = self.player_id
            team = self.team_id
            #assiging_icon
            player.write({
                'icon_player': True,
                'state': 'sold',
                'assigned_team_id': team.id
            })

            team.key_player_ids = [(4, player.id)]

            message = player.name + ' set as Icon player for the team '+ team.name + ' successfully!'
            self.env.user.notify_success(message)


