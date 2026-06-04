# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    hammer_count = fields.Integer(
        string='Counter Hammer Strikes',
        default=3,
        help='Number of hammer strikes shown on owner consoles when Enable Counter is activated.',
    )
    counter_started_at = fields.Datetime(
        string='Counter Started At',
        copy=False,
        help='Set each time the auctioneer activates the countdown. '
             'Owner consoles detect the change and play the mallet animation.',
    )
