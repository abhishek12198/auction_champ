# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .indian_states import GSTIN_RE, INDIAN_STATES, normalize_gstin


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ac_saas_upgrade_payment_enabled = fields.Boolean(
        string='Require Razorpay for SaaS plan upgrades',
        config_parameter='ac_saas_payment.upgrade_payment_enabled',
        help='When enabled, customers must pay the plan package price via Razorpay '
             'before the upgrade is applied. When disabled, they can submit a free '
             'upgrade request for manual approval (existing flow).',
    )
    ac_saas_website_signup_enabled = fields.Boolean(
        string='Enable online plan purchase on website',
        config_parameter='ac_saas_payment.website_signup_enabled',
        default=True,
        help='When enabled, Plans & Pricing shows Get Started and creates a SaaS '
             'login after Razorpay payment. When disabled, Contact Us mailto is used.',
    )
    ac_saas_invoice_legal_name = fields.Char(
        string='Invoice legal name',
        config_parameter='ac_saas_payment.invoice_legal_name',
        default='Auction Champ',
    )
    ac_saas_invoice_address = fields.Char(
        string='Invoice address',
        config_parameter='ac_saas_payment.invoice_address',
    )
    ac_saas_invoice_gstin = fields.Char(
        string='GSTIN',
        config_parameter='ac_saas_payment.invoice_gstin',
    )
    ac_saas_invoice_state = fields.Selection(
        selection=INDIAN_STATES,
        string='Supplier state',
        config_parameter='ac_saas_payment.invoice_state',
    )
    ac_saas_invoice_gst_rate = fields.Float(
        string='GST rate (%)',
        config_parameter='ac_saas_payment.invoice_gst_rate',
        default=18.0,
    )
    ac_saas_invoice_sac = fields.Char(
        string='SAC code',
        config_parameter='ac_saas_payment.invoice_sac',
        default='998313',
    )

    @api.constrains('ac_saas_invoice_gstin')
    def _check_invoice_gstin(self):
        for rec in self:
            gstin = normalize_gstin(rec.ac_saas_invoice_gstin)
            if gstin and not GSTIN_RE.match(gstin):
                raise ValidationError(_('Enter a valid 15-character GSTIN.'))
