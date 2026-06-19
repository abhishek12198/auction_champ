# -*- coding: utf-8 -*-
from odoo import models, fields


class AuctionAdvertiser(models.Model):
    _name = 'auction.advertiser'
    _description = 'Auction Advertiser / Sponsor'
    _order = 'sequence, id'

    name = fields.Char(string='Advertiser / Sponsor Name', required=True)
    image = fields.Binary(
        string='Image / Banner',
        required=True,
        help='Upload a sponsor logo or advertisement banner. '
             'Recommended size: 800×300 px (landscape). PNG or JPG.',
    )
    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament',
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='Display Order', default=10)
    active = fields.Boolean(default=True)
