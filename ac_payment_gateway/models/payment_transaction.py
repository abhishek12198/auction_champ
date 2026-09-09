# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging
import uuid

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RAZORPAY_ORDERS_URL = 'https://api.razorpay.com/v1/orders'


class AcPaymentTransaction(models.Model):
    _name = 'ac.payment.transaction'
    _description = 'AuctionChamp Registration Payment'
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default='New')
    access_token = fields.Char(string='Access Token', copy=False, index=True, default=lambda self: uuid.uuid4().hex)
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
    tournament_id = fields.Many2one('auction.tournament', required=True, ondelete='cascade', index=True)
    player_id = fields.Many2one('auction.team.player', ondelete='set null', index=True)
    payment_mode = fields.Selection(
        [('optional', 'Optional'), ('mandatory', 'Mandatory')],
        required=True,
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.ref('base.INR', raise_if_not_found=False)
            or self.env['res.currency'].search([('name', '=', 'INR')], limit=1)
            or self.env.company.currency_id,
    )
    currency_code = fields.Char(
        related='currency_id.name',
        string='Currency Code',
        store=True,
        readonly=True,
    )
    player_name = fields.Char()
    player_contact = fields.Char()
    player_vals_json = fields.Text(string='Pending Player Data')
    player_photo = fields.Binary(string='Pending Photo', attachment=True)
    razorpay_order_id = fields.Char(index=True, copy=False)
    razorpay_payment_id = fields.Char(index=True, copy=False)
    razorpay_signature = fields.Char(copy=False)
    error_message = fields.Char()

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ac.payment.transaction') or uuid.uuid4().hex[:12].upper()
        return super().create(vals)

    def _amount_to_razorpay_subunit(self):
        """Convert monetary amount to Razorpay's integer subunit (e.g. paise)."""
        self.ensure_one()
        currency = self.currency_id
        decimals = currency.decimal_places if currency else 2
        factor = 10 ** int(decimals or 0)
        return int(round((self.amount or 0.0) * factor))

    def _razorpay_credentials(self):
        ICP = self.env['ir.config_parameter'].sudo()
        key_id = (ICP.get_param('ac_payment_gateway.razorpay_key_id') or '').strip()
        key_secret = (ICP.get_param('ac_payment_gateway.razorpay_key_secret') or '').strip()
        if not key_id or not key_secret:
            raise UserError(_('Razorpay API keys are not configured. '
                              'Go to Auction Settings → Razorpay Payment Gateway.'))
        return key_id, key_secret

    def action_create_razorpay_order(self):
        """Create a Razorpay order and mark transaction pending."""
        self.ensure_one()
        key_id, key_secret = self._razorpay_credentials()
        currency = self.currency_id
        if not currency:
            raise UserError(_('Payment currency is missing on this transaction.'))
        amount_subunit = self._amount_to_razorpay_subunit()
        if amount_subunit < 1:
            raise UserError(_('Registration fee must be greater than zero.'))

        payload = {
            'amount': amount_subunit,
            'currency': (currency.name or 'INR').upper(),
            'receipt': (self.name or 'AC')[:40],
            'notes': {
                'tournament_id': str(self.tournament_id.id),
                'transaction_id': str(self.id),
                'payment_mode': self.payment_mode,
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
            _logger.exception('Razorpay order create failed')
            raise UserError(_('Could not reach Razorpay: %s') % exc) from exc

        self.write({
            'razorpay_order_id': order_id,
            'state': 'pending',
            'error_message': False,
        })
        return {
            'key_id': key_id,
            'order_id': order_id,
            'amount': amount_subunit,
            'currency': (currency.name or 'INR').upper(),
            'name': self.tournament_id.name or 'Registration',
            'description': 'Player registration — %s' % (self.player_name or self.name),
            'prefill': {
                'name': self.player_name or '',
                'contact': self.player_contact or '',
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
        """Verify signature, create player if mandatory, mark paid."""
        self.ensure_one()
        if self.state == 'paid' and self.player_id:
            return self.player_id

        order_id = order_id or self.razorpay_order_id
        if not order_id or not payment_id or not signature:
            raise UserError(_('Incomplete Razorpay payment payload.'))
        if order_id != self.razorpay_order_id:
            raise UserError(_('Razorpay order mismatch.'))
        if not self._verify_signature(order_id, payment_id, signature):
            self.write({'state': 'failed', 'error_message': 'Invalid payment signature'})
            raise UserError(_('Payment verification failed. Invalid signature.'))

        player = self.player_id
        if not player and self.payment_mode == 'mandatory':
            player = self._create_player_from_pending()
        if not player:
            raise UserError(_('No player linked to this payment.'))

        player.sudo().write({
            'amount_paid': True,
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
        })
        self.write({
            'state': 'paid',
            'player_id': player.id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
            'error_message': False,
            'player_vals_json': False,
            'player_photo': False,
        })
        return player

    def _create_player_from_pending(self):
        self.ensure_one()
        if not self.player_vals_json:
            raise UserError(_('Pending registration data is missing.'))
        try:
            vals = json.loads(self.player_vals_json)
        except Exception as exc:
            raise UserError(_('Corrupt pending registration data.')) from exc
        if self.player_photo:
            vals['photo'] = self.player_photo
        vals['amount_paid'] = True
        vals['state'] = 'draft'
        vals['tournament_id'] = self.tournament_id.id
        # Many2many commands may be stored as lists already
        player = self.env['auction.team.player'].sudo().create(vals)
        return player

    @api.model
    def create_for_optional(self, tournament, player):
        tx = self.sudo().create({
            'tournament_id': tournament.id,
            'player_id': player.id,
            'payment_mode': 'optional',
            'amount': tournament.registration_fee,
            'currency_id': tournament.registration_currency_id.id,
            'player_name': player.name,
            'player_contact': player.contact or '',
            'state': 'draft',
        })
        return tx

    @api.model
    def create_for_mandatory(self, tournament, player_vals):
        photo = player_vals.pop('photo', False)
        serializable = {}
        for key, val in player_vals.items():
            if isinstance(val, (list, tuple)):
                serializable[key] = [list(x) if isinstance(x, (list, tuple)) else x for x in val]
            else:
                serializable[key] = val
        tx = self.sudo().create({
            'tournament_id': tournament.id,
            'payment_mode': 'mandatory',
            'amount': tournament.registration_fee,
            'currency_id': tournament.registration_currency_id.id,
            'player_name': serializable.get('name'),
            'player_contact': serializable.get('contact') or '',
            'player_vals_json': json.dumps(serializable),
            'player_photo': photo,
            'state': 'draft',
        })
        return tx
