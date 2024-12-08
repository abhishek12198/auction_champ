# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

import werkzeug
import werkzeug.exceptions


class AuctionTournamentPointSplit(models.Model):
    _name = 'auction.tournament.point.split'

    points = fields.Integer(string="Point")
    no_of_calls = fields.Integer(string="No of Calls")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')


