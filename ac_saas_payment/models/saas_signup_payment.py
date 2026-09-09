# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import re
import secrets
import string
import uuid
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RAZORPAY_ORDERS_URL = 'https://api.razorpay.com/v1/orders'
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class AcSaasSignupPayment(models.Model):
    _name = 'ac.saas.signup.payment'
    _description = 'SaaS Website Plan Signup Payment'
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
            ('provisioned', 'Account Created'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
        index=True,
    )
    plan_id = fields.Many2one(
        'ac.saas.plan', required=True, ondelete='restrict', index=True,
    )
    amount = fields.Monetary(currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', required=True)
    buyer_name = fields.Char(required=True)
    buyer_email = fields.Char(required=True, index=True)
    buyer_phone = fields.Char()
    organization = fields.Char(string='Organisation / Club')
    razorpay_order_id = fields.Char(index=True, copy=False)
    razorpay_payment_id = fields.Char(index=True, copy=False)
    razorpay_signature = fields.Char(copy=False)
    error_message = fields.Char()
    user_id = fields.Many2one('res.users', readonly=True, copy=False)
    account_id = fields.Many2one('ac.saas.account', readonly=True, copy=False)
    credentials_sent = fields.Boolean(default=False, copy=False)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = (
                self.env['ir.sequence'].next_by_code('ac.saas.signup.payment')
                or uuid.uuid4().hex[:10].upper()
            )
        return super().create(vals)

    @api.model
    def website_signup_active(self):
        """Online plan purchase on website: setting ON + Razorpay keys."""
        ICP = self.env['ir.config_parameter'].sudo()
        enabled = (ICP.get_param('ac_saas_payment.website_signup_enabled') or 'True').strip().lower() in (
            '1', 'true', 'yes',
        )
        if not enabled:
            return False
        key_id = (ICP.get_param('ac_payment_gateway.razorpay_key_id') or '').strip()
        key_secret = (ICP.get_param('ac_payment_gateway.razorpay_key_secret') or '').strip()
        return bool(key_id and key_secret)

    @api.model
    def plan_is_purchasable(self, plan):
        plan = plan.sudo()
        if not plan or not plan.active:
            return False
        if float(plan.list_price or 0.0) <= 0:
            return False
        # Custom quote label without treating as payable when price also set is OK —
        # if list_price > 0 we still sell online.
        return True

    @api.model
    def _normalize_email(self, email):
        return (email or '').strip().lower()

    @api.model
    def email_already_registered(self, email):
        email = self._normalize_email(email)
        if not email:
            return False
        Users = self.env['res.users'].sudo()
        return bool(
            Users.search([
                '|',
                ('login', '=ilike', email),
                ('email', '=ilike', email),
            ], limit=1)
        )

    @api.model
    def _validate_buyer(self, name, email, phone=None, organization=None):
        """Fields for SaaS account: name + email login (+ optional phone)."""
        name = (name or '').strip()
        email = self._normalize_email(email)
        phone = (phone or '').strip()
        if not name:
            raise UserError(_('Please enter your full name.'))
        if not email or not EMAIL_RE.match(email):
            raise UserError(_('Please enter a valid email address.'))
        if self.email_already_registered(email):
            raise UserError(_(
                'This email is already registered. Please log in or use a different email.'
            ))
        if not phone:
            raise UserError(_('Please enter your contact number.'))
        if len(re.sub(r'\D', '', phone)) < 7:
            raise UserError(_('Please enter a valid contact number.'))
        return {
            'buyer_name': name,
            'buyer_email': email,
            'buyer_phone': phone or False,
            'organization': (organization or '').strip() or False,
        }

    @api.model
    def create_for_plan(self, plan, buyer_vals):
        plan = plan.sudo()
        if not self.website_signup_active():
            raise UserError(_('Online plan purchase is not enabled.'))
        if not self.plan_is_purchasable(plan):
            raise UserError(_(
                'Plan "%(plan)s" is not available for online purchase. '
                'Please contact sales.'
            ) % {'plan': plan.name})
        amount = float(plan.list_price or 0.0)
        currency = plan.currency_id or self.env.company.currency_id
        vals = dict(buyer_vals)
        vals.update({
            'plan_id': plan.id,
            'amount': amount,
            'currency_id': currency.id,
            'state': 'draft',
        })
        return self.sudo().create(vals)

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
        amount_subunit = self._amount_to_razorpay_subunit()
        if amount_subunit < 1:
            raise UserError(_('Purchase amount must be greater than zero.'))
        payload = {
            'amount': amount_subunit,
            'currency': (self.currency_id.name or 'INR').upper(),
            'receipt': (self.name or 'SSN')[:40],
            'notes': {
                'purpose': 'saas_signup',
                'plan_id': str(self.plan_id.id),
                'email': self.buyer_email or '',
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
            _logger.exception('SaaS signup Razorpay order failed')
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
            'currency': (self.currency_id.name or 'INR').upper(),
            'name': 'AuctionChamp',
            'description': 'Plan purchase — %s' % (self.plan_id.name or self.name),
            'prefill': {
                'name': self.buyer_name or '',
                'email': self.buyer_email or '',
                'contact': self.buyer_phone or '',
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

    @api.model
    def _generate_password(self, length=12):
        alphabet = string.ascii_letters + string.digits
        # Ensure mix of classes
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
        ]
        chars += [secrets.choice(alphabet) for _ in range(max(0, length - 3))]
        secrets.SystemRandom().shuffle(chars)
        return ''.join(chars)

    def action_mark_paid(self, payment_id, signature, order_id=None):
        self.ensure_one()
        if self.state in ('paid', 'provisioned'):
            return self._provision_account()

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
        return self._provision_account()

    def _provision_account(self):
        """Create login user + SaaS account and email credentials."""
        self.ensure_one()
        if self.state == 'provisioned' and self.user_id and self.account_id:
            return {
                'user': self.user_id,
                'account': self.account_id,
                'password': None,
                'already': True,
            }

        if self.user_id and self.account_id:
            self.write({'state': 'provisioned'})
            return {
                'user': self.user_id,
                'account': self.account_id,
                'password': None,
                'already': True,
            }

        # Re-check uniqueness (race after payment)
        Users = self.env['res.users'].sudo()
        existing = Users.search([('login', '=ilike', self.buyer_email)], limit=1)
        if existing:
            # Link if somehow already created for this payment email
            Account = self.env['ac.saas.account'].sudo()
            account = Account.search([('user_id', '=', existing.id)], limit=1)
            if account:
                self.write({
                    'user_id': existing.id,
                    'account_id': account.id,
                    'state': 'provisioned',
                })
                return {
                    'user': existing,
                    'account': account,
                    'password': None,
                    'already': True,
                }
            raise UserError(_(
                'Payment received, but a login already exists for %(email)s. '
                'Please contact support with payment reference %(ref)s.'
            ) % {'email': self.buyer_email, 'ref': self.name})

        password = self._generate_password()
        partner = self.env['res.partner'].sudo().create({
            'name': self.buyer_name,
            'email': self.buyer_email,
            'phone': self.buyer_phone or False,
            'mobile': self.buyer_phone or False,
            'company_type': 'person',
        })

        # Create user with password; suppress Odoo reset-password email.
        user = Users.with_context(no_reset_password=True).create({
            'name': self.buyer_name,
            'login': self.buyer_email,
            'email': self.buyer_email,
            'password': password,
            'partner_id': partner.id,
        })

        plan = self.plan_id
        today = fields.Date.context_today(self)
        validity = int(plan.validity_days or 365)
        account = self.env['ac.saas.account'].sudo().create({
            'name': self.buyer_name,
            'user_id': user.id,
            'plan_id': plan.id,
            'state': 'active',
            'active': True,
            'date_start': today,
            'date_end': today + timedelta(days=validity),
            'notes': _('Created via website signup payment %s') % self.name,
        })

        self.write({
            'user_id': user.id,
            'account_id': account.id,
            'state': 'provisioned',
        })
        self._send_credentials_email(password)
        self._notify_managers_new_signup()
        return {
            'user': user,
            'account': account,
            'password': password,
            'already': False,
        }

    def _login_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return '%s/web/login' % base.rstrip('/')

    def _send_credentials_email(self, password):
        self.ensure_one()
        if self.credentials_sent or not self.buyer_email:
            return
        if 'mail.mail' not in self.env:
            return
        login_url = self._login_url()
        plan = self.plan_id
        account = self.account_id
        body = _(
            '<p>Hi %(name)s,</p>'
            '<p>Welcome to <strong>AuctionChamp</strong>! '
            'Your payment was received and your account is ready.</p>'
            '<ul>'
            '<li>Plan: <strong>%(plan)s</strong></li>'
            '<li>Account: %(account)s</li>'
            '<li>Valid until: %(end)s</li>'
            '<li>Login: <a href="%(url)s">Auction Management Panel</a></li>'
            '<li>Username (email): <strong>%(login)s</strong></li>'
            '<li>Temporary password: <strong>%(password)s</strong></li>'
            '</ul>'
            '<p>Please log in and change your password after first login.</p>'
            '<p>— AuctionChamp Team</p>'
        ) % {
            'name': self.buyer_name,
            'plan': plan.name,
            'account': account.name if account else '',
            'end': account.date_end or '—',
            'url': login_url,
            'login': self.buyer_email,
            'password': password,
        }
        mail = self.env['mail.mail'].sudo().create({
            'subject': _('Your AuctionChamp account — %(plan)s') % {'plan': plan.name},
            'body_html': body,
            'email_to': self.buyer_email,
            'auto_delete': True,
        })
        mail.send()
        self.credentials_sent = True

    def _notify_managers_new_signup(self):
        if 'mail.mail' not in self.env:
            return
        group = self.env.ref('ac_saas_manager.group_saas_manager', raise_if_not_found=False)
        if not group:
            return
        partners = group.users.mapped('partner_id').filtered(lambda p: p.email)
        if not partners:
            return
        for rec in self:
            body = _(
                '<p>New paid website signup <strong>%(ref)s</strong>.</p>'
                '<ul>'
                '<li>Name: %(name)s</li>'
                '<li>Email: %(email)s</li>'
                '<li>Organisation: %(org)s</li>'
                '<li>Plan: %(plan)s</li>'
                '<li>Amount: %(amount)s %(currency)s</li>'
                '<li>Razorpay: %(rzp)s</li>'
                '</ul>'
            ) % {
                'ref': rec.name,
                'name': rec.buyer_name,
                'email': rec.buyer_email,
                'org': rec.organization or '—',
                'plan': rec.plan_id.name,
                'amount': rec.amount,
                'currency': rec.currency_id.name or '',
                'rzp': rec.razorpay_payment_id or '—',
            }
            for partner in partners:
                mail = self.env['mail.mail'].sudo().create({
                    'subject': _('New SaaS signup: %(plan)s — %(email)s') % {
                        'plan': rec.plan_id.name,
                        'email': rec.buyer_email,
                    },
                    'body_html': body,
                    'email_to': partner.email,
                    'auto_delete': True,
                })
                mail.send()
