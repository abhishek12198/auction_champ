# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionPlayerPosition(models.Model):
    _name = 'auction.player.position'
    _description = 'Football Playing Position'
    _order = 'sequence, id'

    name = fields.Char(string='Position', required=True)
    code = fields.Char(string='Code', help='Short code, e.g. GK, CB, ST.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AuctionPlayerStyle(models.Model):
    _name = 'auction.player.style'
    _description = 'Football Playing Style'
    _order = 'sequence, id'

    name = fields.Char(string='Playing Style', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AuctionPlayerStrength(models.Model):
    _name = 'auction.player.strength'
    _description = 'Football Player Strength'
    _order = 'sequence, id'

    name = fields.Char(string='Strength', required=True)
    icon = fields.Char(string='Icon', help='Emoji/icon shown on the chip.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
