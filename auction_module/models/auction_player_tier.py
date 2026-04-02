# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    is_an_icon_tier = fields.Boolean(string='Icon Tier', default=False)

    @api.constrains('is_an_icon_tier')
    def _check_single_icon_tier(self):
        for record in self:
            if record.is_an_icon_tier:
                existing = self.search([
                    ('is_an_icon_tier', '=', True),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError(
                        'Only one tier can be marked as the Icon Tier. '
                        '"%s" is already set as the Icon Tier. '
                        'Please unmark it first before setting a new one.' % existing[0].name
                    )
