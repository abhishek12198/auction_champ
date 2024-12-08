# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class AuctionHistory(models.Model):

    _name = 'auction.history'
    _order = 'id'

    team_id = fields.Many2one('auction.team', 'Team')
    player_photo = fields.Binary()
    message = fields.Char("History Message")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')

