# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    registration_payment_enabled = fields.Boolean(
        string='Include Registration Payment',
        default=False,
        help='When enabled, player registration uses Razorpay for fee collection. '
             'When disabled, the existing QR / payment-proof flow is used.',
    )
    registration_payment_mode = fields.Selection(
        [
            ('optional', 'Optional'),
            ('mandatory', 'Mandatory'),
        ],
        string='Payment Requirement',
        default='optional',
        help='Optional: players can register without paying and pay later.\n'
             'Mandatory: a player is created only after successful Razorpay payment.',
    )
    registration_currency_id = fields.Many2one(
        'res.currency',
        string='Registration Currency',
        default=lambda self: self.env.ref('base.INR', raise_if_not_found=False)
            or self.env['res.currency'].search([('name', '=', 'INR')], limit=1)
            or self.env.company.currency_id,
        help='Currency for the player registration fee (from Accounting currencies). Defaults to INR.',
    )
    registration_fee = fields.Monetary(
        string='Registration Fee',
        currency_field='registration_currency_id',
        default=0.0,
        help='Amount charged via Razorpay for player registration.',
    )

    @api.constrains(
        'registration_payment_enabled',
        'registration_fee',
        'registration_currency_id',
    )
    def _check_registration_fee(self):
        for rec in self:
            if not rec.registration_payment_enabled:
                continue
            if not rec.registration_currency_id:
                raise ValidationError(
                    'Please select a Registration Currency when '
                    'Include Registration Payment is enabled.'
                )
            if (rec.registration_fee or 0) <= 0:
                raise ValidationError(
                    'Please set a Registration Fee greater than zero when '
                    'Include Registration Payment is enabled.'
                )

    def ac_razorpay_active(self):
        """True when Razorpay should drive registration payment for this tournament."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        key_id = (ICP.get_param('ac_payment_gateway.razorpay_key_id') or '').strip()
        key_secret = (ICP.get_param('ac_payment_gateway.razorpay_key_secret') or '').strip()
        return bool(
            self.registration_payment_enabled
            and (self.registration_fee or 0) > 0
            and self.registration_currency_id
            and key_id
            and key_secret
        )

    def ac_registration_fee_label(self):
        """Human-readable fee with currency, e.g. ₹ 500.00."""
        self.ensure_one()
        from odoo.tools.misc import formatLang
        return formatLang(
            self.env,
            self.registration_fee or 0.0,
            currency_obj=self.registration_currency_id,
        )
