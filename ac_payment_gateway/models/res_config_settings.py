# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ac_razorpay_key_id = fields.Char(
        string='Razorpay Key ID',
        config_parameter='ac_payment_gateway.razorpay_key_id',
    )
    ac_razorpay_key_secret = fields.Char(
        string='Razorpay Key Secret',
        config_parameter='ac_payment_gateway.razorpay_key_secret',
    )
    ac_razorpay_webhook_secret = fields.Char(
        string='Razorpay Webhook Secret',
        config_parameter='ac_payment_gateway.razorpay_webhook_secret',
        help='Optional. Used to validate Razorpay webhook callbacks.',
    )
