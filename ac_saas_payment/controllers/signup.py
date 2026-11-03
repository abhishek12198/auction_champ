# -*- coding: utf-8 -*-
import json
import logging
import re

import werkzeug
from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

from odoo.addons.ac_saas_payment.models.phone_countries import (
    detect_signup_country_code,
    signup_phone_rows,
    split_signup_phone,
)
from odoo.addons.ac_saas_payment.models.visitor_country import (
    apply_country_cookie,
)

_logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class SaasSignupPaymentController(http.Controller):

    def _client_ip(self):
        req = request.httprequest
        forwarded = (req.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        return forwarded or (req.remote_addr or '')

    def _get_signup(self, token):
        Signup = request.env['ac.saas.signup.payment'].sudo()
        rec = Signup.search([('access_token', '=', token)], limit=1)
        if not rec:
            raise NotFound()
        return rec

    def _money(self, currency, amount):
        decimals = int(currency.decimal_places) if currency else 2
        text = ('{:,.%df}' % max(0, decimals)).format(amount or 0)
        sym = ''
        if currency:
            sym = currency.symbol or currency.name or ''
        return ('%s %s' % (sym, text)).strip()

    def _checkout_payload(self, payment):
        if not payment.razorpay_order_id:
            return payment.action_create_razorpay_order()
        key_id = payment._razorpay_credentials()[0]
        return {
            'key_id': key_id,
            'order_id': payment.razorpay_order_id,
            'amount': payment._amount_to_razorpay_subunit(),
            'currency': (payment.currency_id.name or 'INR').upper(),
            'name': 'AuctionChamp',
            'description': 'Plan purchase — %s' % (payment.plan_id.name or payment.name),
            'prefill': {
                'name': payment.buyer_name or '',
                'email': payment.buyer_email or '',
                'contact': payment.buyer_phone or '',
            },
            'transaction_token': payment.access_token,
        }

    @http.route(
        '/saas/signup/<int:plan_id>',
        type='http', auth='public', website=True, sitemap=False,
        methods=['GET', 'POST'], csrf=True,
    )
    def saas_signup_form(self, plan_id, **post):
        Signup = request.env['ac.saas.signup.payment'].sudo()
        plan = request.env['ac.saas.plan'].sudo().browse(plan_id).exists()
        if not plan or not plan.active:
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': _('This plan is not available.'),
            })

        explicit = post.get('billing_country_code') or post.get('country') or ''
        price_ctx = Signup.website_price_context(explicit or None)
        country = price_ctx['country']
        quote = plan.get_price_for_country(country)

        if not Signup.website_signup_active() or not quote['purchasable']:
            config = request.env['auction.website.config'].sudo().get_singleton()
            email = (config.contact_email or '').strip() or 'support@auctionchamp.in'
            if quote['matched_region'] and country:
                message = _(
                    'Online purchase of %(plan)s is not available in %(country)s yet. '
                    'Please contact us at %(email)s.'
                ) % {'plan': plan.name, 'country': country.name, 'email': email}
            else:
                message = _(
                    'Online purchase is not available for this plan. '
                    'Please contact us at %s.'
                ) % email
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': message,
            })

        price_info = plan.get_website_price_display(country)
        detected_code = detect_signup_country_code(self._client_ip())
        currency = quote['currency'] or plan.currency_id
        card_note = False
        if currency and (currency.name or '').upper() != 'INR':
            card_note = _(
                'You will pay by international card in %s.'
            ) % currency.name
        ctx = {
            'plan': plan,
            'amount_label': self._money(currency, quote['amount']),
            'price_validity': price_info.get('validity') or '',
            'price_country_name': price_ctx['country_name'],
            'billing_country_code': price_ctx['country_code'] or '__default__',
            'billing_countries': price_ctx['countries'],
            'card_note': card_note,
            'error': False,
            'email_error': False,
            'phone_error': False,
            'form': {
                'buyer_name': '',
                'buyer_email': '',
                'buyer_country_code': detected_code,
                'buyer_phone_national': '',
            },
            'phone_countries': signup_phone_rows(detected_code),
        }

        if request.httprequest.method == 'POST':
            country_code = post.get('buyer_country_code') or detected_code
            national = post.get('buyer_phone_national') or ''
            code, national_digits = split_signup_phone(
                '%s%s' % (country_code, re.sub(r'\D', '', national))
            )
            form = {
                'buyer_name': post.get('buyer_name') or '',
                'buyer_email': post.get('buyer_email') or '',
                'buyer_country_code': code,
                'buyer_phone_national': national_digits,
            }
            ctx['form'] = form
            ctx['phone_countries'] = signup_phone_rows(code)
            try:
                buyer = Signup._validate_buyer(
                    form['buyer_name'],
                    form['buyer_email'],
                    '%s%s' % (code, national_digits),
                )
                payment = Signup.create_for_plan(plan, buyer, country=country)
                payment.action_create_razorpay_order()
                response = werkzeug.utils.redirect(
                    '/saas/signup/pay/%s' % payment.access_token, 303,
                )
                return apply_country_cookie(
                    response, country.code if country else '__default__',
                )
            except UserError as exc:
                msg = str(exc)
                ctx['error'] = msg
                if 'already registered' in msg.lower() or 'already exists' in msg.lower():
                    ctx['email_error'] = msg
                elif 'digit' in msg.lower() or 'contact number' in msg.lower() or 'country code' in msg.lower():
                    ctx['phone_error'] = msg
            except Exception as exc:
                _logger.exception('SaaS signup form failed')
                ctx['error'] = str(exc)

        response = request.render('ac_saas_payment.saas_signup_form', ctx)
        chosen = (post.get('country') or '').strip()
        if request.httprequest.method == 'GET' and chosen:
            apply_country_cookie(response, chosen)
        return response

    @http.route(
        '/saas/signup/check_email',
        type='json', auth='public', website=True, csrf=False, methods=['POST'],
    )
    def saas_signup_check_email(self, email=None, **kw):
        email = email or kw.get('email') or ''
        Signup = request.env['ac.saas.signup.payment'].sudo()
        email = Signup._normalize_email(email)
        if not email:
            return {'ok': True, 'taken': False, 'message': ''}
        if not __import__('re').match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return {
                'ok': False,
                'taken': False,
                'message': _('Please enter a valid email address.'),
            }
        taken = Signup.email_already_registered(email)
        return {
            'ok': not taken,
            'taken': taken,
            'message': _(
                'This email is already registered. Please log in or use a different email.'
            ) if taken else '',
        }

    @http.route(
        '/saas/signup/pay/<string:token>',
        type='http', auth='public', website=False, sitemap=False, csrf=False,
    )
    def saas_signup_pay(self, token, **kw):
        payment = self._get_signup(token)
        if payment.state == 'provisioned' or (
            payment.state == 'paid' and payment.user_id
        ):
            return werkzeug.utils.redirect(
                '/saas/signup/done/%s' % payment.access_token, 303,
            )

        if payment.state in ('cancelled', 'failed'):
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': _('This purchase is no longer available.'),
                'payment': payment,
            })

        try:
            checkout = self._checkout_payload(payment)
        except Exception as exc:
            _logger.exception('SaaS signup checkout failed')
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': str(exc),
                'payment': payment,
            })

        verify_url = '/saas/signup/pay/%s/verify' % payment.access_token
        auto_open = kw.get('auto') != '0'
        return request.render('ac_saas_payment.saas_signup_pay', {
            'payment': payment,
            'plan': payment.plan_id,
            'amount_label': self._money(payment.currency_id, payment.amount),
            'razorpay_checkout': checkout,
            'razorpay_checkout_json': json.dumps(checkout or {}).replace('<', '\\u003c'),
            'razorpay_verify_url': verify_url,
            'razorpay_auto_open': auto_open,
            'home_url': '/',
        })

    @http.route(
        '/saas/signup/pay/<string:token>/verify',
        type='json', auth='public', website=False, csrf=False, methods=['POST'],
    )
    def saas_signup_verify(self, token, **kw):
        payment = self._get_signup(token)
        payment_id = kw.get('razorpay_payment_id') or kw.get('payment_id')
        order_id = kw.get('razorpay_order_id') or kw.get('order_id')
        signature = kw.get('razorpay_signature') or kw.get('signature')
        try:
            payment.action_mark_paid(payment_id, signature, order_id=order_id)
            return {
                'ok': True,
                'redirect_url': '/saas/signup/done/%s' % payment.access_token,
            }
        except Exception as exc:
            _logger.exception('SaaS signup verify failed')
            return {'ok': False, 'error': str(exc)}

    @http.route(
        '/saas/signup/done/<string:token>',
        type='http', auth='public', website=False, sitemap=False, csrf=False,
    )
    def saas_signup_done(self, token, **kw):
        payment = self._get_signup(token)
        if payment.state not in ('paid', 'provisioned'):
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': _('Payment is not complete yet.'),
                'payment': payment,
            })
        try:
            if payment.state != 'provisioned' or not payment.user_id:
                payment._provision_account()
        except Exception as exc:
            _logger.exception('SaaS signup provision on done page failed')
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': _(
                    'Payment received, but account setup needs attention. '
                    'Please contact support with reference %(ref)s. (%(err)s)'
                ) % {'ref': payment.name, 'err': str(exc)},
                'payment': payment,
            })

        return request.render('ac_saas_payment.saas_signup_done', {
            'payment': payment,
            'plan': payment.plan_id,
            'login_url': payment._login_url(),
            'login': payment.buyer_email,
            'account': payment.account_id,
        })
