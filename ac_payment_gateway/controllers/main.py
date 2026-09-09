# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import urlencode

import werkzeug
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.auction_module.controllers.main import Auction, _build_player_vals_from_post

_logger = logging.getLogger(__name__)


class AuctionPaymentRegister(Auction):
    """Razorpay hooks for player registration (active only when tournament flag is on)."""

    def _ac_checkout_payload(self, tournament, tx):
        """Build / refresh Razorpay checkout dict for a transaction."""
        if not tx.razorpay_order_id:
            return tx.action_create_razorpay_order()
        return {
            'key_id': tx._razorpay_credentials()[0],
            'order_id': tx.razorpay_order_id,
            'amount': tx._amount_to_razorpay_subunit(),
            'currency': (tx.currency_id.name or 'INR').upper(),
            'name': tournament.name or 'Registration',
            'description': 'Player registration — %s' % (tx.player_name or tx.name),
            'prefill': {'name': tx.player_name or '', 'contact': tx.player_contact or ''},
            'transaction_token': tx.access_token,
        }

    def _ac_checkout_json(self, checkout):
        return json.dumps(checkout or {}).replace('<', '\\u003c')

    def _ac_register_path(self, db_name, tournament_slug, render_ctx=None, tournament=None):
        """Public or admin registration path (admin when unlocked / flagged)."""
        admin = False
        if render_ctx and render_ctx.get('admin_registration'):
            admin = True
        elif render_ctx and render_ctx.get('register_path'):
            return render_ctx.get('register_path')
        elif tournament and request.session.get('ac_reg_admin_unlocked_%s' % int(tournament.id)):
            admin = True
        path = '/%s/%s/player/register' % (db_name, tournament_slug)
        return path + '/admin' if admin else path

    def _ac_register_pay_url(self, db_name, tournament_slug, pay_token, await_payment=True,
                             render_ctx=None, tournament=None):
        qs = urlencode({
            'await_payment': '1' if await_payment else '0',
            'pay_token': pay_token,
        })
        path = self._ac_register_path(db_name, tournament_slug, render_ctx=render_ctx, tournament=tournament)
        return '%s?%s' % (path, qs)

    def _registration_payment_post(self, db_name, tournament_slug, tournament, render_ctx):
        if not tournament.ac_razorpay_active():
            return None

        Tx = request.env['ac.payment.transaction'].sudo()
        mode = tournament.registration_payment_mode or 'optional'
        try:
            vals = _build_player_vals_from_post(request, tournament)
            # Online payment replaces QR / proof upload
            vals.pop('payment_proof', None)

            if mode == 'mandatory':
                tx = Tx.create_for_mandatory(tournament, vals)
                tx.action_create_razorpay_order()
                # Stay on themed registration page; Razorpay opens as overlay.
                return werkzeug.utils.redirect(
                    self._ac_register_pay_url(
                        db_name, tournament_slug, tx.access_token, await_payment=True,
                        render_ctx=render_ctx, tournament=tournament,
                    ),
                    303,
                )

            player = request.env['auction.team.player'].sudo().create(vals)
            player.write({'amount_paid': False})
            tx = Tx.create_for_optional(tournament, player)
            tx.action_create_razorpay_order()
            qs = urlencode({
                'success': '1',
                'player_id': player.id,
                'pay_token': tx.access_token,
            })
            path = self._ac_register_path(
                db_name, tournament_slug, render_ctx=render_ctx, tournament=tournament)
            return werkzeug.utils.redirect('%s?%s' % (path, qs), 303)
        except Exception as e:
            _logger.exception('Razorpay registration POST failed')
            html = request.render('auction_module.player_registration_form', dict(render_ctx, **{
                'error': str(e),
                'razorpay_enabled': True,
                'razorpay_mode': mode,
                'registration_fee': tournament.registration_fee,
                'registration_fee_label': tournament.ac_registration_fee_label(),
                'registration_currency': tournament.registration_currency_id,
            }), lazy=False)
            return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    def _registration_payment_get_ctx(self, ctx, tournament, kw):
        if not tournament.ac_razorpay_active():
            ctx['razorpay_enabled'] = False
            ctx['razorpay_await_payment'] = False
            return ctx

        ctx['razorpay_enabled'] = True
        ctx['razorpay_mode'] = tournament.registration_payment_mode
        ctx['registration_fee'] = tournament.registration_fee
        ctx['registration_fee_label'] = tournament.ac_registration_fee_label()
        ctx['registration_currency'] = tournament.registration_currency_id
        reg_path = ctx.get('register_path') or self._ac_register_path(
            ctx.get('db_name') or '', ctx.get('tournament_slug') or tournament.slug or '',
            render_ctx=ctx, tournament=tournament,
        )
        ctx['register_path'] = reg_path
        ctx['razorpay_verify_url'] = '/{}/{}/player/register/payment/verify'.format(
            ctx.get('db_name') or '', ctx.get('tournament_slug') or tournament.slug or ''
        )
        ctx['razorpay_await_payment'] = False
        ctx['razorpay_checkout'] = False
        ctx['razorpay_checkout_json'] = '{}'
        ctx['razorpay_auto_open'] = False

        if kw.get('paid') == '1':
            ctx['success'] = True
            ctx['payment_just_completed'] = True
            try:
                ctx['player_id'] = int(kw.get('player_id')) if kw.get('player_id') else ctx.get('player_id')
            except (TypeError, ValueError):
                pass
            return ctx

        pay_token = kw.get('pay_token') or False
        ctx['razorpay_pay_token'] = pay_token

        # Mandatory: pending payment after submit — keep themed page + overlay checkout
        if kw.get('await_payment') == '1' and pay_token:
            tx = request.env['ac.payment.transaction'].sudo().search(
                [('access_token', '=', pay_token), ('tournament_id', '=', tournament.id)],
                limit=1,
            )
            if tx and tx.state == 'paid' and tx.player_id:
                ctx['success'] = True
                ctx['payment_just_completed'] = True
                ctx['player_id'] = tx.player_id.id
                ctx['razorpay_await_payment'] = False
                return ctx
            if tx and tx.state != 'paid':
                try:
                    checkout = self._ac_checkout_payload(tournament, tx)
                    ctx['razorpay_await_payment'] = True
                    ctx['razorpay_checkout'] = checkout
                    ctx['razorpay_checkout_json'] = self._ac_checkout_json(checkout)
                    ctx['razorpay_auto_open'] = True
                    ctx['razorpay_tx'] = tx
                except Exception as e:
                    _logger.exception('Failed to prepare Razorpay checkout for await_payment')
                    ctx['razorpay_await_payment'] = True
                    ctx['error'] = str(e)
            return ctx

        needs_payment = False
        player_id = ctx.get('player_id')
        if ctx.get('success') and player_id and tournament.registration_payment_mode == 'optional':
            player = request.env['auction.team.player'].sudo().browse(player_id)
            if player.exists() and not player.amount_paid:
                needs_payment = True
                if pay_token:
                    tx = request.env['ac.payment.transaction'].sudo().search(
                        [('access_token', '=', pay_token), ('tournament_id', '=', tournament.id)],
                        limit=1,
                    )
                    if tx and tx.state != 'paid':
                        try:
                            checkout = self._ac_checkout_payload(tournament, tx)
                            ctx['razorpay_checkout'] = checkout
                            ctx['razorpay_checkout_json'] = self._ac_checkout_json(checkout)
                        except Exception:
                            _logger.exception('Failed to prepare optional Razorpay checkout')
        ctx['razorpay_needs_payment'] = needs_payment
        return ctx

    def _ac_render_checkout(self, db_name, tournament_slug, tournament, tx, checkout):
        """Legacy standalone page — redirect to themed registration overlay instead."""
        return werkzeug.utils.redirect(
            self._ac_register_pay_url(
                db_name, tournament_slug, tx.access_token, await_payment=True,
                tournament=tournament,
            ),
            303,
        )

    @http.route('/<string:db_name>/<string:tournament_slug>/player/register/payment/verify',
                type='json', auth='none', website=False, csrf=False, methods=['POST'])
    def player_register_payment_verify(self, db_name, tournament_slug, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return {'ok': False, 'error': 'Database not found'}
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tournament:
                return {'ok': False, 'error': 'Tournament not found'}

            token = kw.get('token') or kw.get('transaction_token')
            payment_id = kw.get('razorpay_payment_id')
            order_id = kw.get('razorpay_order_id')
            signature = kw.get('razorpay_signature')

            tx = request.env['ac.payment.transaction'].sudo().search(
                [('access_token', '=', token), ('tournament_id', '=', tournament.id)], limit=1
            )
            if not tx:
                return {'ok': False, 'error': 'Payment session not found'}
            try:
                player = tx.action_mark_paid(payment_id, signature, order_id=order_id)
                path = self._ac_register_path(
                    db_name, tournament_slug, tournament=tournament)
                redirect = '%s?paid=1&player_id=%s' % (path, player.id)
                return {'ok': True, 'player_id': player.id, 'redirect': redirect}
            except Exception as e:
                _logger.exception('payment verify failed')
                return {'ok': False, 'error': str(e)}

    @http.route('/<string:db_name>/<string:tournament_slug>/player/register/payment/checkout/<string:token>',
                type='http', auth='none', website=False, methods=['GET'], csrf=False)
    def player_register_payment_checkout(self, db_name, tournament_slug, token, **kw):
        """Redirect old checkout URLs onto the themed registration page."""
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()
            tournament = request.env['auction.tournament'].sudo().search(
                [('slug', '=', tournament_slug)], limit=1
            )
            if not tournament or not tournament.ac_razorpay_active():
                return self._not_found()
            tx = request.env['ac.payment.transaction'].sudo().search(
                [('access_token', '=', token), ('tournament_id', '=', tournament.id)], limit=1
            )
            if not tx:
                raise NotFound()
            path = self._ac_register_path(db_name, tournament_slug, tournament=tournament)
            if tx.state == 'paid' and tx.player_id:
                return werkzeug.utils.redirect(
                    '%s?paid=1&player_id=%s' % (path, tx.player_id.id), 303
                )
            # Optional mode: prefer success page with in-place pay button
            if tx.payment_mode == 'optional' and tx.player_id:
                qs = urlencode({
                    'success': '1',
                    'player_id': tx.player_id.id,
                    'pay_token': tx.access_token,
                })
                return werkzeug.utils.redirect('%s?%s' % (path, qs), 303)
            return werkzeug.utils.redirect(
                self._ac_register_pay_url(
                    db_name, tournament_slug, tx.access_token, await_payment=True,
                    tournament=tournament,
                ),
                303,
            )


# Bind hooks onto auction_module's Auction controller (owns /player/register).
Auction._registration_payment_post = AuctionPaymentRegister._registration_payment_post
Auction._registration_payment_get_ctx = AuctionPaymentRegister._registration_payment_get_ctx
Auction._ac_render_checkout = AuctionPaymentRegister._ac_render_checkout
