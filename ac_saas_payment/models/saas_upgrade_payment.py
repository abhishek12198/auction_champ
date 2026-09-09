# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import uuid

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RAZORPAY_ORDERS_URL = 'https://api.razorpay.com/v1/orders'


class AcSaasUpgradePayment(models.Model):
    _name = 'ac.saas.upgrade.payment'
    _description = 'SaaS Plan Upgrade Payment'
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, default='New')
    access_token = fields.Char(
        copy=False, index=True, default=lambda self: uuid.uuid4().hex,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('pending', 'Pending Payment'),
            ('paid', 'Paid'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
        index=True,
    )
    upgrade_request_id = fields.Many2one(
        'ac.saas.upgrade.request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    account_id = fields.Many2one(
        related='upgrade_request_id.account_id',
        store=True,
        readonly=True,
    )
    plan_id = fields.Many2one(
        related='upgrade_request_id.requested_plan_id',
        store=True,
        readonly=True,
    )
    amount = fields.Monetary(currency_field='currency_id', required=True)
    list_price_amount = fields.Monetary(
        string='New plan price',
        currency_field='currency_id',
        help='Full package price of the target plan before proration credit.',
    )
    credit_amount = fields.Monetary(
        string='Prorated credit',
        currency_field='currency_id',
        help='Unused value credited from the current package.',
    )
    proration_note = fields.Char(string='Proration note')
    currency_id = fields.Many2one('res.currency', required=True)
    razorpay_order_id = fields.Char(index=True, copy=False)
    razorpay_payment_id = fields.Char(index=True, copy=False)
    razorpay_signature = fields.Char(copy=False)
    error_message = fields.Char()

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = (
                self.env['ir.sequence'].next_by_code('ac.saas.upgrade.payment')
                or uuid.uuid4().hex[:10].upper()
            )
        return super().create(vals)

    @api.model
    def saas_upgrade_payment_setting_on(self):
        """True when the SaaS manager setting is enabled (keys may still be missing)."""
        ICP = self.env['ir.config_parameter'].sudo()
        return (ICP.get_param('ac_saas_payment.upgrade_payment_enabled') or '').strip().lower() in (
            '1', 'true', 'yes',
        )

    @api.model
    def saas_upgrade_payment_active(self):
        """True when paid upgrades are enabled AND Razorpay keys are configured."""
        if not self.saas_upgrade_payment_setting_on():
            return False
        ICP = self.env['ir.config_parameter'].sudo()
        key_id = (ICP.get_param('ac_payment_gateway.razorpay_key_id') or '').strip()
        key_secret = (ICP.get_param('ac_payment_gateway.razorpay_key_secret') or '').strip()
        return bool(key_id and key_secret)

    def _amount_to_razorpay_subunit(self):
        self.ensure_one()
        decimals = self.currency_id.decimal_places if self.currency_id else 2
        factor = 10 ** int(decimals or 0)
        return int(round((self.amount or 0.0) * factor))

    def _razorpay_credentials(self):
        ICP = self.env['ir.config_parameter'].sudo()
        key_id = (ICP.get_param('ac_payment_gateway.razorpay_key_id') or '').strip()
        key_secret = (ICP.get_param('ac_payment_gateway.razorpay_key_secret') or '').strip()
        if not key_id or not key_secret:
            raise UserError(_(
                'Razorpay API keys are not configured. '
                'Go to Settings → Razorpay Payment Gateway.'
            ))
        return key_id, key_secret

    def action_create_razorpay_order(self):
        self.ensure_one()
        key_id, key_secret = self._razorpay_credentials()
        if not self.currency_id:
            raise UserError(_('Payment currency is missing.'))
        amount_subunit = self._amount_to_razorpay_subunit()
        if amount_subunit < 1:
            raise UserError(_('Upgrade amount must be greater than zero.'))

        payload = {
            'amount': amount_subunit,
            'currency': (self.currency_id.name or 'INR').upper(),
            'receipt': (self.name or 'SUP')[:40],
            'notes': {
                'purpose': 'saas_upgrade',
                'upgrade_request_id': str(self.upgrade_request_id.id),
                'account_id': str(self.account_id.id),
                'plan_id': str(self.plan_id.id),
            },
        }
        try:
            resp = requests.post(
                RAZORPAY_ORDERS_URL,
                json=payload,
                auth=(key_id, key_secret),
                timeout=30,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                msg = data.get('error', {}).get('description') or resp.text or 'Order create failed'
                raise UserError(_('Razorpay error: %s') % msg)
            order_id = data.get('id')
            if not order_id:
                raise UserError(_('Razorpay did not return an order id.'))
        except UserError:
            raise
        except Exception as exc:
            _logger.exception('SaaS upgrade Razorpay order failed')
            raise UserError(_('Could not reach Razorpay: %s') % exc) from exc

        self.write({
            'razorpay_order_id': order_id,
            'state': 'pending',
            'error_message': False,
        })
        user = self.upgrade_request_id.user_id
        return {
            'key_id': key_id,
            'order_id': order_id,
            'amount': amount_subunit,
            'currency': (self.currency_id.name or 'INR').upper(),
            'name': 'AuctionChamp',
            'description': 'Plan upgrade — %s' % (self.plan_id.name or self.name),
            'prefill': {
                'name': user.name or '',
                'email': user.email or '',
                'contact': (user.partner_id.mobile or user.partner_id.phone or '') if user.partner_id else '',
            },
            'transaction_token': self.access_token,
        }

    def _verify_signature(self, order_id, payment_id, signature):
        _key_id, key_secret = self._razorpay_credentials()
        body = '%s|%s' % (order_id, payment_id)
        expected = hmac.new(
            key_secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature or '')

    def action_mark_paid(self, payment_id, signature, order_id=None):
        self.ensure_one()
        if self.state == 'paid':
            return self.upgrade_request_id

        order_id = order_id or self.razorpay_order_id
        if not order_id or not payment_id or not signature:
            raise UserError(_('Incomplete Razorpay payment payload.'))
        if order_id != self.razorpay_order_id:
            raise UserError(_('Razorpay order mismatch.'))
        if not self._verify_signature(order_id, payment_id, signature):
            self.write({'state': 'failed', 'error_message': 'Invalid payment signature'})
            raise UserError(_('Payment verification failed. Invalid signature.'))

        self.write({
            'state': 'paid',
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
            'error_message': False,
        })
        request = self.upgrade_request_id.sudo()
        request._saas_apply_paid_upgrade(payment=self)
        return request

    @api.model
    def create_for_upgrade_request(
        self, upgrade_request, amount=None,
        list_price_amount=None, credit_amount=None, proration_note=None,
    ):
        upgrade_request.ensure_one()
        plan = upgrade_request.requested_plan_id
        if amount is None:
            amount = plan.list_price or 0.0
        currency = plan.currency_id or self.env.company.currency_id
        if amount <= 0:
            raise UserError(_(
                'Plan %(plan)s has no payable upgrade amount after proration. '
                'Set package prices or disable paid upgrades.'
            ) % {'plan': plan.name})
        return self.sudo().create({
            'upgrade_request_id': upgrade_request.id,
            'amount': amount,
            'list_price_amount': list_price_amount if list_price_amount is not None else amount,
            'credit_amount': credit_amount or 0.0,
            'proration_note': proration_note or False,
            'currency_id': currency.id,
            'state': 'draft',
        })
