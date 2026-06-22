# -*- coding: utf-8 -*-
from odoo import models, fields


class AuctionWebsitePricing(models.Model):
    _name = 'auction.website.pricing'
    _description = 'AuctionChamp Website Pricing Plan'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Plan Name', required=True)
    subtitle = fields.Char(
        string='Subtitle',
        help='Short description shown below the plan name, e.g. "Perfect for small leagues"',
    )
    badge = fields.Char(
        string='Badge Label',
        help='Highlighted badge shown on the card, e.g. "Most Popular"',
    )
    features = fields.Text(
        string='Features',
        help='One feature per line. These are listed on the pricing card.',
    )
    contact_url = fields.Char(
        string='Contact / Sign-up URL',
        default='mailto:sales@auctionchamp.in',
    )
    is_highlighted = fields.Boolean(
        string='Highlight this plan',
        default=False,
        help='Visually emphasises this plan (larger card, coloured border).',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
