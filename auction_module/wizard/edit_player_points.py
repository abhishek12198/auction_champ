# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class EditPlayerPoints(models.TransientModel):
    _name = 'auction.edit.player.point'

    points = fields.Integer()
    previous_points = fields.Integer()
    points_gain = fields.Integer()
    player_id = fields.Many2one('auction.team.player', 'Player')
    player_photo = fields.Binary(related='player_id.photo')
    contact = fields.Char(related='player_id.contact')

    @api.model
    def default_get(self, fields):
        defaults = super(EditPlayerPoints, self).default_get(fields)
        if self.env.context.get('active_id', False):
            player_line = self.env['auction.auction.player'].browse(self.env.context.get('active_id', False))
            if player_line:
                defaults.update({'player_id': player_line.player_id.id, 'points': player_line.points, 'previous_points': player_line.points})

        return defaults

    @api.onchange('previous_points', 'points')
    def onchange_points(self):
        self.points_gain = self.previous_points - self.points

    def button_update_points(self):
        player_line_id = self.env.context.get('active_id', False)
        if player_line_id:
            player_line = self.env['auction.auction.player'].browse(player_line_id)
            player_line.points = self.points
            message = 'Points updated for the player '+player_line.player_id.name +' updated successfully'
            self.env.user.notify_success(message)


