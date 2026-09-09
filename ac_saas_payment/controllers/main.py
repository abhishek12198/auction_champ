# -*- coding: utf-8 -*-
import json
import logging

from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class SaasUpgradePaymentController(http.Controller):

    def _get_payment(self, token):
        Payment = request.env['ac.saas.upgrade.payment'].sudo()
        payment = Payment.search([('access_token', '=', token)], limit=1)
        if not payment:
            raise NotFound()
        return payment

    def _assert_owner(self, payment):
        user = request.env.user
        if user._is_public():
            return False
        account_user = payment.upgrade_request_id.account_id.user_id
        if account_user == user:
            return True
        if (
            user.has_group('ac_saas_manager.group_saas_manager')
            or user.has_group('auction_module.group_auction_group_admin')
            or user._is_superuser()
        ):
            return True
        return False

    def _checkout_payload(self, payment):
        if not payment.razorpay_order_id:
            return payment.action_create_razorpay_order()
        key_id = payment._razorpay_credentials()[0]
        user = payment.upgrade_request_id.user_id
        return {
            'key_id': key_id,
            'order_id': payment.razorpay_order_id,
            'amount': payment._amount_to_razorpay_subunit(),
            'currency': (payment.currency_id.name or 'INR').upper(),
            'name': 'AuctionChamp',
            'description': 'Plan upgrade — %s' % (payment.plan_id.name or payment.name),
            'prefill': {
                'name': user.name or '',
                'email': user.email or '',
                'contact': (
                    user.partner_id.mobile or user.partner_id.phone or ''
                ) if user.partner_id else '',
            },
            'transaction_token': payment.access_token,
        }

    @http.route(
        '/saas/upgrade/pay/<string:token>',
        type='http', auth='user', website=False, sitemap=False, csrf=False,
    )
    def saas_upgrade_pay(self, token, **kw):
        payment = self._get_payment(token)
        if not self._assert_owner(payment):
            return request.make_response(
                _('You are not allowed to pay for this upgrade.'),
                status=403,
            )

        req = payment.upgrade_request_id
        if req.state == 'approved' or payment.state == 'paid':
            return request.render('ac_saas_payment.saas_upgrade_pay_done', {
                'payment': payment,
                'upgrade_request': req,
                'plan': req.requested_plan_id,
            })

        if req.state != 'awaiting_payment' or payment.state in ('cancelled', 'failed'):
            return request.render('ac_saas_payment.saas_upgrade_pay_error', {
                'message': _('This upgrade payment is no longer available.'),
                'payment': payment,
            })

        try:
            checkout = self._checkout_payload(payment)
        except Exception as exc:
            _logger.exception('SaaS upgrade checkout payload failed')
            return request.render('ac_saas_payment.saas_upgrade_pay_error', {
                'message': str(exc),
                'payment': payment,
            })

        verify_url = '/saas/upgrade/pay/%s/verify' % payment.access_token
        auto_open = kw.get('auto') != '0' and kw.get('done') != '1'
        cur = payment.currency_id
        sym = (cur.symbol or cur.name or '') if cur else ''

        def _money(val):
            return ('%s %s' % (sym, '{:,.2f}'.format(val or 0))).strip()

        return request.render('ac_saas_payment.saas_upgrade_pay', {
            'payment': payment,
            'upgrade_request': req,
            'plan': req.requested_plan_id,
            'current_plan': req.current_plan_id,
            'amount_label': _money(payment.amount),
            'list_price_label': _money(payment.list_price_amount),
            'credit_label': _money(payment.credit_amount),
            'show_proration': bool(payment.list_price_amount or payment.credit_amount),
            'proration_note': payment.proration_note or '',
            'razorpay_checkout': checkout,
            'razorpay_checkout_json': json.dumps(checkout or {}).replace('<', '\\u003c'),
            'razorpay_verify_url': verify_url,
            'razorpay_verify_url_js': json.dumps(verify_url),
            'razorpay_auto_open': auto_open,
            'razorpay_auto_open_js': 'true' if auto_open else 'false',
            'backend_url': '/web',
        })

    @http.route(
        '/saas/upgrade/pay/<string:token>/verify',
        type='json', auth='user', website=False, csrf=False, methods=['POST'],
    )
    def saas_upgrade_verify(self, token, **kw):
        payment = self._get_payment(token)
        if not self._assert_owner(payment):
            return {'ok': False, 'error': 'Access denied'}

        payment_id = kw.get('razorpay_payment_id') or kw.get('payment_id')
        order_id = kw.get('razorpay_order_id') or kw.get('order_id')
        signature = kw.get('razorpay_signature') or kw.get('signature')
        try:
            payment.action_mark_paid(payment_id, signature, order_id=order_id)
            return {
                'ok': True,
                'redirect_url': '/saas/upgrade/pay/%s?done=1' % payment.access_token,
            }
        except Exception as exc:
            _logger.exception('SaaS upgrade payment verify failed')
            return {'ok': False, 'error': str(exc)}
