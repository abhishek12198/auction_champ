# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    website_calendar_visible = fields.Boolean(
        string='Show on Website Calendar',
        default=False,
        help='When enabled, this tournament is listed on the public /calendar page '
             '(logo, dates, and venue), including after it is archived. '
             'When disabled, it is hidden from the calendar even if it is live, '
             'open for registration, or archived.',
    )
