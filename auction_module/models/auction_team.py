# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionTeam(models.Model):
    _name = 'auction.team'

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        return defaults

    active = fields.Boolean(default=True)
    name = fields.Char(string="Team Name", required=True)
    logo = fields.Binary(string="Team Logo",
                            help="Add team logo")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    manager = fields.Char('Owner')
    key_player_ids = fields.Many2many('auction.team.player', 'team_player_rel', 'team_id', 'player_id', 'Icon Players')
