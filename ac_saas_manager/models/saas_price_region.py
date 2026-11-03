# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Currencies Razorpay can charge. INR is domestic. The others need
# International payments enabled on the Razorpay account. The customer
# pays the currency configured here; Razorpay settles rupees in India.
RAZORPAY_CURRENCY_CODES = (
    'INR', 'USD', 'EUR', 'GBP', 'AED', 'SAR', 'QAR', 'SGD', 'AUD', 'CAD',
    'JPY', 'CNY', 'HKD', 'NZD', 'CHF', 'SEK', 'NOK', 'DKK', 'THB', 'MYR',
    'ZAR', 'KWD', 'BHD', 'OMR', 'PHP', 'IDR', 'KRW', 'LKR', 'NPR', 'BDT',
    'MUR', 'CZK', 'HUF', 'ILS', 'MXN', 'PLN',
)


class AcSaasPriceRegion(models.Model):
    _name = 'ac.saas.price.region'
    _description = 'SaaS Price Region'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        domain=lambda self: [('name', 'in', list(RAZORPAY_CURRENCY_CODES))],
    )
    country_ids = fields.Many2many(
        'res.country',
        'ac_saas_price_region_country_rel',
        'region_id',
        'country_id',
        string='Countries',
    )
    plan_price_ids = fields.One2many(
        'ac.saas.plan.price',
        'region_id',
        string='Plan prices',
    )

    @api.constrains('currency_id')
    def _check_currency_supported(self):
        for region in self:
            code = (region.currency_id.name or '').upper()
            if code and code not in RAZORPAY_CURRENCY_CODES:
                raise ValidationError(_(
                    'Razorpay cannot charge %(currency)s. Choose a supported currency.'
                ) % {'currency': code})

    @api.constrains('country_ids', 'active')
    def _check_country_once(self):
        for region in self:
            if not region.active or not region.country_ids:
                continue
            others = self.search([
                ('id', '!=', region.id),
                ('active', '=', True),
                ('country_ids', 'in', region.country_ids.ids),
            ])
            overlap = region.country_ids & others.mapped('country_ids')
            if overlap:
                raise ValidationError(_(
                    '%(countries)s already belong to another price region. '
                    'A country can be in only one active region.'
                ) % {'countries': ', '.join(overlap.mapped('name'))})

    @api.model
    def _activate_razorpay_currencies(self):
        """Make Razorpay currencies selectable the first time this runs.

        Later upgrades leave the list alone, so a currency turned off in
        Accounting stays off.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('ac_saas_manager.razorpay_currencies_ready'):
            return True
        currencies = self.env['res.currency'].with_context(active_test=False).search([
            ('name', 'in', list(RAZORPAY_CURRENCY_CODES)),
        ])
        inactive = currencies.filtered(lambda currency: not currency.active)
        if inactive:
            inactive.write({'active': True})
        ICP.set_param('ac_saas_manager.razorpay_currencies_ready', '1')
        return True


class AcSaasPlanPrice(models.Model):
    _name = 'ac.saas.plan.price'
    _description = 'SaaS Plan Regional Price'
    _order = 'region_id, id'

    plan_id = fields.Many2one(
        'ac.saas.plan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    region_id = fields.Many2one(
        'ac.saas.price.region',
        string='Region',
        required=True,
        ondelete='restrict',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='region_id.currency_id',
        store=True,
        readonly=True,
    )
    price = fields.Monetary(
        string='Package price',
        currency_field='currency_id',
        required=True,
    )
    price_per_tournament = fields.Monetary(
        string='Per tournament',
        currency_field='currency_id',
        compute='_compute_price_per_tournament',
    )

    _sql_constraints = [
        (
            'plan_region_uniq',
            'unique(plan_id, region_id)',
            'This region is already priced on the plan.',
        ),
    ]

    @api.depends('price', 'plan_id.max_tournaments', 'currency_id')
    def _compute_price_per_tournament(self):
        for line in self:
            tournaments = int(line.plan_id.max_tournaments or 0)
            amount = float(line.price or 0.0)
            line.price_per_tournament = (amount / tournaments) if tournaments else 0.0

    @api.constrains('price')
    def _check_price_positive(self):
        for line in self:
            if float(line.price or 0.0) <= 0:
                raise ValidationError(_(
                    'Regional package price must be greater than zero.'
                ))
