# -*- coding: utf-8 -*-
import base64
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AcSaasAccount(models.Model):
    _inherit = 'ac.saas.account'

    def action_request_reactivation(self):
        """Collect Razorpay for same-plan renewal when paid upgrades are on."""
        self.ensure_one()
        Payment = self.env['ac.saas.upgrade.payment']
        plan = self.plan_id
        quote = plan.get_price_for_country(self.billing_country_id) if plan else None
        if Payment.saas_upgrade_payment_active() and quote and quote['matched_region'] and not quote['purchasable']:
            raise UserError(_(
                'Plan "%(plan)s" has no regional price for %(country)s. '
                'Add it on the SaaS plan before renewing.'
            ) % {
                'plan': plan.name,
                'country': self.billing_country_id.display_name,
            })
        if Payment.saas_upgrade_payment_active() and quote and quote['purchasable']:
            return self._saas_start_paid_renewal()
        return super().action_request_reactivation()

    def _approved_renewal_count(self):
        """Count Razorpay-paid renewals even if the request row lagged on approve."""
        self.ensure_one()
        count = super()._approved_renewal_count()
        if not isinstance(self.id, int):
            return count
        paid_unapproved = self.env['ac.saas.upgrade.payment'].sudo().search_count([
            ('account_id', '=', self.id),
            ('state', '=', 'paid'),
            ('upgrade_request_id.trigger_feature', '=', 'renewal'),
            ('upgrade_request_id.state', '!=', 'approved'),
        ])
        return count + paid_unapproved

    def _saas_start_paid_renewal(self):
        """Create a same-plan renewal checkout at the full package price."""
        self.ensure_one()
        self._assert_can_request_renewal()
        plan = self.plan_id
        if not plan:
            raise UserError(_('No SaaS plan is assigned to this account.'))

        quote = plan.get_price_for_country(self.billing_country_id)
        amount = float(quote['amount'] or 0.0)
        currency = quote['currency'] or self.env.company.currency_id
        if not quote['purchasable'] or amount <= 0:
            if quote['matched_region'] and self.billing_country_id:
                raise UserError(_(
                    'Plan "%(plan)s" has no regional price for %(country)s. '
                    'Add it on the SaaS plan, or turn off Razorpay for plan upgrades.'
                ) % {
                    'plan': plan.name,
                    'country': self.billing_country_id.display_name,
                })
            raise UserError(_(
                'Plan "%(plan)s" has no package price. Set Package price on the '
                'SaaS plan, or turn off Razorpay for plan upgrades.'
            ) % {'plan': plan.name})

        Payment = self.env['ac.saas.upgrade.payment']
        if not Payment.saas_upgrade_payment_active():
            raise UserError(_(
                'Razorpay payment is required to renew this plan, but API keys '
                'are not configured. Ask your administrator to set Razorpay keys '
                'under Settings → Razorpay Payment Gateway.'
            ))

        Request = self.env['ac.saas.upgrade.request'].sudo()
        pending = Request.search([
            ('account_id', '=', self.id),
            ('state', 'in', ('pending', 'awaiting_payment')),
            ('trigger_feature', '=', 'renewal'),
        ], limit=1)
        validity = int(plan.validity_days or 365)
        proration_note = _(
            'Full package price for a new %(days)s-day term on %(plan)s.'
        ) % {'days': validity, 'plan': plan.name}

        if pending:
            if pending.state == 'awaiting_payment' and pending.payment_ids:
                pay = pending.payment_ids.filtered(
                    lambda p: p.state in ('draft', 'pending')
                )[:1]
                if pay:
                    vals = {
                        'amount': amount,
                        'list_price_amount': amount,
                        'credit_amount': 0.0,
                        'proration_note': proration_note,
                        'currency_id': currency.id,
                    }
                    if (
                        abs((pay.amount or 0.0) - amount) > 0.001
                        or pay.currency_id != currency
                    ):
                        vals.update({'razorpay_order_id': False, 'state': 'draft'})
                    pay.write(vals)
                    if not pay.razorpay_order_id:
                        pay.action_create_razorpay_order()
                    return {
                        'type': 'ir.actions.act_url',
                        'url': '/saas/upgrade/pay/%s' % pay.access_token,
                        'target': 'self',
                    }
            pending.write({'state': 'cancelled'})
            pending.payment_ids.filtered(
                lambda p: p.state in ('draft', 'pending')
            ).write({'state': 'cancelled'})

        request = Request.create({
            'account_id': self.id,
            'current_plan_id': plan.id,
            'requested_plan_id': plan.id,
            'trigger_feature': 'renewal',
            'note': self._renewal_customer_note(),
            'state': 'awaiting_payment',
            'payment_required': True,
        })
        payment = Payment.create_for_upgrade_request(
            request,
            amount=amount,
            list_price_amount=amount,
            credit_amount=0.0,
            proration_note=proration_note,
            currency=currency,
        )
        payment.action_create_razorpay_order()
        return {
            'type': 'ir.actions.act_url',
            'url': '/saas/upgrade/pay/%s' % payment.access_token,
            'target': 'self',
        }

    def action_send_credentials_email(self, password=None, email_to=None, extra_attachments=None):
        """Attach the website signup invoice, then send the welcome letter."""
        self.ensure_one()
        attachments = list(extra_attachments or [])
        signup = self.env['ac.saas.signup.payment'].sudo().search([
            ('account_id', '=', self.id),
            ('state', 'in', ('paid', 'provisioned')),
        ], order='id desc', limit=1)
        if signup and not any(
            len(item) > 2 and item[2] == 'application/pdf' for item in attachments
        ):
            try:
                stored = signup.with_context(bin_size=False)._invoice_attachment()
                raw = stored.with_context(bin_size=False).datas if stored else False
                if raw:
                    attachments.append((
                        stored.name,
                        base64.b64decode(raw),
                        'application/pdf',
                    ))
            except Exception:
                _logger.exception(
                    'Could not build the signup invoice for account %s (signup %s)',
                    self.id, signup.name,
                )
        return super().action_send_credentials_email(
            password=password,
            email_to=email_to,
            extra_attachments=attachments,
        )
