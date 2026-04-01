# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionPlayerTier(models.Model):
    _name = 'auction.player.tier'
    _description = 'Auction Player Tier'

    name = fields.Char(string='Tier Name', required=True)
    description = fields.Char(string='Description')
    color = fields.Selection([
        ('#e74c3c', 'Red'),
        ('#e67e22', 'Orange'),
        ('#f39c12', 'Yellow'),
        ('#2ecc71', 'Green'),
        ('#1abc9c', 'Teal'),
        ('#3498db', 'Blue'),
        ('#2980b9', 'Dark Blue'),
        ('#9b59b6', 'Purple'),
        ('#e91e63', 'Pink'),
        ('#34495e', 'Dark'),
        ('#7f8c8d', 'Gray'),
        ('#ffffff', 'White'),
    ], string='Color', default='#3498db')
