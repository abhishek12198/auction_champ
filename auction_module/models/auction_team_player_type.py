# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions

class PlayerType(models.Model):
    _name = 'auction.team.player.type'

    name = fields.Char(string="Type of the player", required=True)
    base_point = fields.Integer(string="Base point to call")



