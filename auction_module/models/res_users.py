# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionTeam(models.Model):
    _inherit = 'res.users'

    tournament_ids = fields.Many2many('auction.tournament', 'auction_tournament_user_rel', 'user_id', 'tournament_id', 'Tournaments')
    