# -*- coding: utf-8 -*-
from odoo import fields, models


class AuctionTeamPlayer(models.Model):
    _inherit = 'auction.team.player'

    razorpay_order_id = fields.Char(string='Razorpay Order ID', copy=False, index=True)
    razorpay_payment_id = fields.Char(string='Razorpay Payment ID', copy=False, index=True)
