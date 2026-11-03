# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import string
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .indian_states import GSTIN_RE, INDIAN_STATE_NAMES, normalize_gstin
from .phone_countries import compose_signup_phone, split_signup_phone

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
    invoice_number = fields.Char(copy=False, index=True, readonly=True)
    invoice_date = fields.Date(copy=False, readonly=True)
    buyer_gstin = fields.Char(string='Buyer GSTIN', copy=False)
    buyer_state = fields.Char(string='Buyer State', copy=False)
    buyer_country_id = fields.Many2one(
        'res.country',
        string='Billing country',
        copy=False,
        help='Country chosen at checkout. Empty means the plan’s standard price.',
    )
    supplier_name = fields.Char(readonly=True, copy=False)
    supplier_address = fields.Char(readonly=True, copy=False)
    supplier_gstin = fields.Char(readonly=True, copy=False)
    supplier_state = fields.Char(readonly=True, copy=False)
    sac_code = fields.Char(readonly=True, copy=False)
    gst_rate = fields.Float(readonly=True, copy=False, digits=(16, 2))
    taxable_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    cgst_rate = fields.Float(readonly=True, copy=False, digits=(16, 2))
    cgst_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    sgst_rate = fields.Float(readonly=True, copy=False, digits=(16, 2))
    sgst_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    igst_rate = fields.Float(readonly=True, copy=False, digits=(16, 2))
    igst_amount = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    place_of_supply = fields.Char(readonly=True, copy=False)
    tax_snapshotted = fields.Boolean(default=False, copy=False)

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
    def plan_is_purchasable(self, plan, country=None):
        plan = plan.sudo()
        if not plan or not plan.active:
            return False
        if country:
            return bool(plan.get_price_for_country(country)['purchasable'])
        if float(plan.list_price or 0.0) <= 0:
            return False
        # Custom quote label without treating as payable when price also set is OK —
        # if list_price > 0 we still sell online.
        return True

    @api.model
    def website_price_context(self, explicit_code=None):
        """Countries for the pricing selector, plus the resolved billing country."""
        from odoo.http import request
        from .visitor_country import resolve_country_iso

        geoip_code = ''
        httprequest = None
        try:
            httprequest = request.httprequest
            geoip_code = (request.session.get('geoip') or {}).get('country_code') or ''
        except RuntimeError:
            httprequest = None
        iso = ''
        if httprequest is not None:
            iso = resolve_country_iso(httprequest, explicit_code, geoip_code)
        elif explicit_code and len((explicit_code or '').strip()) == 2:
            iso = explicit_code.strip().upper()
        Country = self.env['res.country'].sudo()
        countries = Country.search([('code', '!=', False)], order='name')
        selected = countries.filtered(lambda country: country.code == iso)[:1] if iso else Country.browse()
        rows = [{
            'code': country.code,
            'name': country.name,
            'selected': bool(selected) and country.id == selected.id,
        } for country in countries]
        return {
            'country': selected,
            'countries': rows,
            'country_name': selected.name if selected else '',
            'country_code': selected.code if selected else '',
        }

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
    def _validate_buyer(self, name, email, phone=None, organization=None, gstin=None, state=None):
        """Fields for SaaS account: name + email login (+ optional phone)."""
        name = (name or '').strip()
        email = self._normalize_email(email)
        phone = (phone or '').strip()
        gstin = normalize_gstin(gstin)
        state = (state or '').strip()
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
        code, national = split_signup_phone(phone)
        try:
            phone = compose_signup_phone(code, national)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        if gstin and not GSTIN_RE.match(gstin):
            raise UserError(_('Enter a valid 15-character GSTIN, or leave it blank.'))
        if state and state not in INDIAN_STATE_NAMES:
            raise UserError(_('Select a state from the list, or leave it blank.'))
        return {
            'buyer_name': name,
            'buyer_email': email,
            'buyer_phone': phone or False,
            'organization': (organization or '').strip() or False,
            'buyer_gstin': gstin or False,
            'buyer_state': state or False,
        }

    @api.model
    def create_for_plan(self, plan, buyer_vals, country=None):
        plan = plan.sudo()
        if not self.website_signup_active():
            raise UserError(_('Online plan purchase is not enabled.'))
        quote = plan.get_price_for_country(country)
        if not quote['purchasable']:
            if quote['matched_region'] and country:
                raise UserError(_(
                    'Plan "%(plan)s" has no price for %(country)s. '
                    'Please choose another country or contact sales.'
                ) % {'plan': plan.name, 'country': country.name})
            raise UserError(_(
                'Plan "%(plan)s" is not available for online purchase. '
                'Please contact sales.'
            ) % {'plan': plan.name})
        amount = float(quote['amount'] or 0.0)
        currency = quote['currency'] or plan.currency_id or self.env.company.currency_id
        vals = dict(buyer_vals)
        vals.update({
            'plan_id': plan.id,
            'amount': amount,
            'currency_id': currency.id,
            'buyer_country_id': country.id if country else False,
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
                'country': self.buyer_country_id.code or '',
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
                if self.buyer_country_id and not account.billing_country_id:
                    account.write({'billing_country_id': self.buyer_country_id.id})
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
            'billing_country_id': self.buyer_country_id.id or False,
            'state': 'active',
            'active': True,
            'date_start': today,
            'date_end': today + timedelta(days=validity),
            'notes': _('Created via website signup payment %s') % self.name,
        })
        if self.buyer_country_id and partner:
            partner.sudo().write({'country_id': self.buyer_country_id.id})

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
        return self.env['ac.saas.account']._saas_login_url()

    def _assign_invoice(self):
        """Give a paid website signup a stable invoice number, date, and GST split."""
        for rec in self:
            if rec.state not in ('paid', 'provisioned'):
                continue
            vals = {}
            if not rec.invoice_number:
                vals['invoice_number'] = (
                    self.env['ir.sequence'].sudo().next_by_code('ac.saas.signup.invoice')
                    or 'INV%s' % rec.id
                )
                vals['invoice_date'] = rec.invoice_date or fields.Date.context_today(rec)
            if not rec.tax_snapshotted:
                vals.update(rec._invoice_tax_snapshot())
                vals['tax_snapshotted'] = True
            if vals:
                rec.write(vals)
        return True

    @api.model
    def _money(self, amount):
        return float(Decimal(str(amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _invoice_tax_snapshot(self):
        """GST included in the amount already paid. Frozen on the invoice."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        foreign = bool(
            self.buyer_country_id and (self.buyer_country_id.code or '') != 'IN'
        )
        raw_rate = ICP.get_param('ac_saas_payment.invoice_gst_rate')
        rate = 0.0 if foreign else (
            18.0 if raw_rate in (None, False, '') else float(raw_rate)
        )
        if rate < 0:
            rate = 0.0
        legal_name = (ICP.get_param('ac_saas_payment.invoice_legal_name') or '').strip() or 'Auction Champ'
        address = (ICP.get_param('ac_saas_payment.invoice_address') or '').strip()
        gstin = normalize_gstin(ICP.get_param('ac_saas_payment.invoice_gstin'))
        supplier_state = (ICP.get_param('ac_saas_payment.invoice_state') or '').strip()
        sac = (ICP.get_param('ac_saas_payment.invoice_sac') or '').strip() or '998313'
        buyer_state = (self.buyer_state or '').strip()
        total = self._money(self.amount)
        if rate:
            taxable = self._money(total * 100.0 / (100.0 + rate))
            tax = self._money(total - taxable)
        else:
            taxable = total
            tax = 0.0
        interstate = bool(
            buyer_state and supplier_state
            and buyer_state.lower() != supplier_state.lower()
        )
        if interstate:
            cgst = sgst = 0.0
            igst = tax
            cgst_rate = sgst_rate = 0.0
            igst_rate = rate
        else:
            cgst = self._money(tax / 2.0)
            sgst = self._money(tax - cgst)
            igst = 0.0
            half = rate / 2.0
            cgst_rate = sgst_rate = half
            igst_rate = 0.0
        return {
            'supplier_name': legal_name,
            'supplier_address': address or False,
            'supplier_gstin': gstin or False,
            'supplier_state': supplier_state or False,
            'sac_code': sac,
            'gst_rate': rate,
            'taxable_amount': taxable,
            'cgst_rate': cgst_rate,
            'cgst_amount': cgst,
            'sgst_rate': sgst_rate,
            'sgst_amount': sgst,
            'igst_rate': igst_rate,
            'igst_amount': igst,
            'place_of_supply': (
                self.buyer_country_id.name if foreign
                else (buyer_state or supplier_state or False)
            ),
        }

    def _rate_label(self, rate):
        rate = float(rate or 0.0)
        if abs(rate - round(rate)) < 0.001:
            return '%d' % int(round(rate))
        text = ('%.2f' % rate).rstrip('0').rstrip('.')
        return text

    def _invoice_amount_words(self):
        self.ensure_one()
        currency = self.currency_id
        if not currency:
            return ''
        try:
            return currency.amount_to_text(self.amount or 0.0)
        except Exception:
            return ''

    def _invoice_filename(self):
        self.ensure_one()
        safe = (self.invoice_number or self.name or 'invoice').replace('/', '-')
        return 'AuctionChamp-Invoice-%s.pdf' % safe

    def _format_money(self, amount):
        self.ensure_one()
        currency = self.currency_id
        decimals = int(currency.decimal_places if currency else 2)
        text = ('{:,.%df}' % max(0, decimals)).format(float(amount or 0.0))
        symbol = (currency.symbol or '').strip()
        if symbol and symbol.isascii():
            if currency.position == 'after':
                return '%s %s' % (text, symbol)
            return '%s %s' % (symbol, text)
        code = (currency.name or '').strip()
        return '%s %s' % (code, text) if code else text

    def _invoice_date_label(self):
        self.ensure_one()
        return self.env['ac.saas.account']._saas_format_date(self.invoice_date)

    def _invoice_valid_until_label(self):
        self.ensure_one()
        account = self.account_id
        if account and account.date_end:
            return self.env['ac.saas.account']._saas_format_date(account.date_end)
        if self.invoice_date and self.plan_id:
            end = self.invoice_date + timedelta(days=int(self.plan_id.validity_days or 365))
            return self.env['ac.saas.account']._saas_format_date(end)
        return ''

    def _invoice_logo_data_uri(self):
        path = os.path.normpath(os.path.join(
            os.path.dirname(__file__),
            '..', 'static', 'src', 'img', 'invoice_wordmark.png',
        ))
        try:
            with open(path, 'rb') as handle:
                raw = handle.read()
        except OSError:
            return ''
        return 'data:image/png;base64,%s' % base64.b64encode(raw).decode('ascii')

    def _invoice_attachment(self):
        """Render the subscription invoice and store it on this payment."""
        self.ensure_one()
        self._assign_invoice()
        if not self.invoice_number:
            return self.env['ir.attachment']
        report = self.env.ref(
            'ac_saas_payment.action_report_saas_signup_invoice',
            raise_if_not_found=False,
        )
        if not report:
            _logger.error('Subscription invoice report is not installed')
            return self.env['ir.attachment']
        pdf, _ctype = report.with_context(
            ac_saas_invoice_internal=True,
        )._render_qweb_pdf(self.ids)
        filename = self._invoice_filename()
        Attachment = self.env['ir.attachment'].sudo()
        existing = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', '=', filename),
        ], limit=1)
        vals = {
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        }
        if existing:
            existing.write(vals)
            return existing
        return Attachment.create(vals)

    def action_print_invoice(self):
        self.ensure_one()
        if self.state not in ('paid', 'provisioned'):
            raise UserError(_(
                'An invoice is created after the website subscription payment is received.'
            ))
        self._assign_invoice()
        return self.env.ref(
            'ac_saas_payment.action_report_saas_signup_invoice'
        ).report_action(self)

    def _send_credentials_email(self, password):
        """Delegate to ac_saas_manager so credential mail lives on the account."""
        self.ensure_one()
        if self.credentials_sent or not self.buyer_email:
            return
        account = self.account_id
        if not account:
            _logger.warning(
                'Signup %s has no SaaS account; credentials email skipped',
                self.name,
            )
            return
        ok = account.action_send_credentials_email(
            password=password,
            email_to=self.buyer_email,
        )
        if ok:
            self.credentials_sent = True
        else:
            _logger.warning(
                'Credentials email failed for signup %s (%s); '
                'account is provisioned — use Email login credentials on the SaaS account',
                self.name, self.buyer_email,
            )

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
                '<li>Invoice: %(invoice)s</li>'
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
                'invoice': rec.invoice_number or '—',
                'rzp': rec.razorpay_payment_id or '—',
            }
            for partner in partners:
                try:
                    mail = self.env['mail.mail'].sudo().create({
                        'subject': _('New SaaS signup: %(plan)s — %(email)s') % {
                            'plan': rec.plan_id.name,
                            'email': rec.buyer_email,
                        },
                        'body_html': body,
                        'email_from': self.env['ac.saas.account']._saas_email_from(),
                        'email_to': partner.email,
                        'auto_delete': True,
                    })
                    mail.sudo().send()
                except Exception:
                    _logger.exception(
                        'Failed to notify SaaS manager %s about signup %s',
                        partner.email, rec.name,
                    )


class ReportSaasSignupInvoice(models.AbstractModel):
    _name = 'report.ac_saas_payment.report_saas_signup_invoice'
    _description = 'Auction Champ subscription invoice'

    @api.model
    def _get_report_values(self, docids, data=None):
        user = self.env.user
        is_manager = (
            user.has_group('ac_saas_manager.group_saas_manager')
            or user.has_group('auction_module.group_auction_group_admin')
        )
        public_user = self.env.ref('base.public_user', raise_if_not_found=False)
        website_checkout = bool(
            self.env.context.get('ac_saas_invoice_internal')
            and public_user
            and user.id == public_user.id
        )
        if not is_manager and not website_checkout:
            raise AccessError(_('You cannot download this invoice.'))
        docs = self.env['ac.saas.signup.payment'].sudo().browse(docids)
        docs._assign_invoice()
        return {
            'doc_ids': docids,
            'doc_model': 'ac.saas.signup.payment',
            'docs': docs,
        }
