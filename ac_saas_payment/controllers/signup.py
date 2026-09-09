# -*- coding: utf-8 -*-
import json
import logging
import re

import werkzeug
from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class SaasSignupPaymentController(http.Controller):

    def _get_signup(self, token):
        Signup = request.env['ac.saas.signup.payment'].sudo()
        rec = Signup.search([('access_token', '=', token)], limit=1)
        if not rec:
            raise NotFound()
        return rec

    def _money(self, currency, amount):
        sym = ''
        if currency:
            sym = currency.symbol or currency.name or ''
        return ('%s %s' % (sym, '{:,.2f}'.format(amount or 0))).strip()

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

        if not Signup.website_signup_active() or not Signup.plan_is_purchasable(plan):
            config = request.env['auction.website.config'].sudo().get_singleton()
            email = (config.contact_email or '').strip() or 'support@auctionchamp.in'
            return request.render('ac_saas_payment.saas_signup_error', {
                'message': _(
                    'Online purchase is not available for this plan. '
                    'Please contact us at %s.'
                ) % email,
            })

        price_info = plan.get_website_price_display()
        ctx = {
            'plan': plan,
            'amount_label': self._money(plan.currency_id, plan.list_price),
            'price_validity': price_info.get('validity') or '',
            'error': False,
            'email_error': False,
            'form': {
                'buyer_name': '',
                'buyer_email': '',
                'buyer_phone': '',
            },
        }

        if request.httprequest.method == 'POST':
            form = {
                'buyer_name': post.get('buyer_name') or '',
                'buyer_email': post.get('buyer_email') or '',
                'buyer_phone': post.get('buyer_phone') or '',
            }
            ctx['form'] = form
            try:
                buyer = Signup._validate_buyer(
                    form['buyer_name'],
                    form['buyer_email'],
                    form['buyer_phone'],
                )
                payment = Signup.create_for_plan(plan, buyer)
                payment.action_create_razorpay_order()
                return werkzeug.utils.redirect(
                    '/saas/signup/pay/%s' % payment.access_token, 303,
                )
            except UserError as exc:
                msg = str(exc)
                ctx['error'] = msg
                if 'already registered' in msg.lower() or 'already exists' in msg.lower():
                    ctx['email_error'] = msg
            except Exception as exc:
                _logger.exception('SaaS signup form failed')
                ctx['error'] = str(exc)

        return request.render('ac_saas_payment.saas_signup_form', ctx)

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
