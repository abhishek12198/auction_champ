# -*- coding: utf-8 -*-
from odoo import fields, models


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
