# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions


class AuctionTournament(models.Model):
    _name = 'auction.tournament'

    @api.model
    def default_get(self, fields):
        defaults = super(AuctionTournament, self).default_get(fields)
        existing_tournament = self.search([])
        if existing_tournament:
            raise ValidationError("Current Tournament is active. Please deactivate and create a new one.")

        return defaults

    name = fields.Char(string="Name", required=True)
    description = fields.Char(string="Short Description", required=True)
    venue = fields.Text("Venue")
    logo = fields.Binary('Logo')
    active = fields.Boolean(default=True)
    player_appearance_algorithm = fields.Selection([('linear', 'Linear'), ('random', 'Random')], default="linear")
    team_max_points = fields.Integer(string="Max points alloted for a team")
    organizer_uid = fields.Many2one('res.users', 'Organizer')
    points_split_ids = fields.One2many('auction.tournament.point.split', 'tournament_id', 'Points Split')

    organizer_uids = fields.Many2many('res.users', 'auction_tournament_user_rel', 'tournament_id', 'user_id',
                                      'Organizers')

    team_ids = fields.One2many('auction.team', 'tournament_id', 'Teams')
    template_image = fields.Binary('Template Image')
    report_footer = fields.Binary('Footer')
    rules_regulations = fields.Html("Rules and Regulations")