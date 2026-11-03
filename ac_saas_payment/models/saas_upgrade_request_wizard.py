# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AcSaasUpgradeRequestWizard(models.TransientModel):
    _inherit = 'ac.saas.upgrade.request.wizard'

    payment_required = fields.Boolean(
        string='Payment required',
        compute='_compute_payment_required',
    )
    upgrade_amount = fields.Monetary(
        string='Amount to pay',
        currency_field='upgrade_currency_id',
        compute='_compute_payment_required',
    )
    upgrade_list_price = fields.Monetary(
        string='New plan price',
        currency_field='upgrade_currency_id',
        compute='_compute_payment_required',
    )
    upgrade_credit = fields.Monetary(
        string='Prorated credit',
        currency_field='upgrade_currency_id',
        compute='_compute_payment_required',
    )
    upgrade_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_payment_required',
    )
    upgrade_amount_label = fields.Char(
        compute='_compute_payment_required',
    )
    upgrade_proration_note = fields.Char(
        compute='_compute_payment_required',
    )

    @api.model
    def _saas_upgrade_payment_setting_on(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return (ICP.get_param('ac_saas_payment.upgrade_payment_enabled') or '').strip().lower() in (
            '1', 'true', 'yes',
        )

    def _account_billing_country(self):
        self.ensure_one()
        account = self.account_id
        if account and account.billing_country_id:
            return account.billing_country_id
        return self.env['res.country']

    def _saas_plan_allows_free_request(self, plan):
        """Only custom-quote plans (price label, no package price) skip Razorpay.

        Note: ``contact_support`` means “beyond this plan, contact support” —
        it must NOT skip payment when upgrading *to* that plan.
        A missing regional price is not a free upgrade.
        """
        self.ensure_one()
        if not plan:
            return False
        quote = plan.get_price_for_country(self._account_billing_country())
        if quote['matched_region'] and not quote['purchasable']:
            return False
        if quote['purchasable']:
            return False
        if (plan.price_label or '').strip():
            return True
        return False

    def _regional_price_error(self, details):
        """Message when the locked billing country cannot be priced. Else False."""
        self.ensure_one()
        country = self._account_billing_country()
        country_name = country.display_name if country else _('this account')
        if details.get('currency_mismatch'):
            return _(
                'The current plan and the new plan use different currencies for %(country)s. '
                'Set both prices in the same currency on the SaaS plans.'
            ) % {'country': country_name}
        if details.get('unavailable') == 'target':
            return _(
                'Plan "%(plan)s" has no regional price for %(country)s. '
                'Add it on the SaaS plan before taking payment.'
            ) % {
                'plan': self.requested_plan_id.name,
                'country': country_name,
            }
        if details.get('unavailable') == 'current':
            return _(
                'The current plan has no regional price for %(country)s, so the unused '
                'credit cannot be calculated. Add that price on the SaaS plan.'
            ) % {'country': country_name}
        return False

    def _money_round(self, amount, currency):
        if currency:
            return currency.round(amount or 0.0)
        return round(amount or 0.0, 2)

    def _saas_upgrade_proration(self):
        """Prorated upgrade: new package price minus unused credit on current package.

        Prices follow the account’s billing country. No billing country, or a
        country outside every region, uses each plan’s standard package price.
        credit = current price × (remaining_days / period_days)
        amount = max(0, new price − credit)
        """
        self.ensure_one()
        plan = self.requested_plan_id
        current = self.current_plan_id
        account = self.account_id
        country = self._account_billing_country()
        target_quote = plan.get_price_for_country(country) if plan else None
        current_quote = current.get_price_for_country(country) if current else None
        company_currency = self.env.company.currency_id
        currency = (
            (target_quote or {}).get('currency')
            or company_currency
        )
        target = float((target_quote or {}).get('amount') or 0.0)
        current_price = float((current_quote or {}).get('amount') or 0.0)
        unavailable = False
        currency_mismatch = False
        renewal = self.trigger_feature == 'renewal'
        if target_quote and target_quote['matched_region'] and not target_quote['purchasable']:
            unavailable = 'target'
            target = 0.0
        elif (
            not renewal
            and current_quote
            and current_quote['matched_region']
            and not current_quote['purchasable']
        ):
            unavailable = 'current'
            current_price = 0.0
        if (
            not renewal
            and not unavailable
            and target_quote and current_quote
            and target_quote['purchasable'] and current_quote['purchasable']
            and target_quote['currency'] and current_quote['currency']
            and target_quote['currency'] != current_quote['currency']
        ):
            currency_mismatch = True

        today = fields.Date.context_today(self)
        period_days = 0
        remaining_days = 0

        if renewal:
            period_days = max(1, int((plan.validity_days if plan else 0) or 365))
            return {
                'target': target,
                'current_price': current_price,
                'credit': 0.0,
                'amount': self._money_round(target, currency),
                'period_days': period_days,
                'remaining_days': 0,
                'ratio': 0.0,
                'currency': currency,
                'unavailable': unavailable,
                'currency_mismatch': currency_mismatch,
            }

        if account and account.date_start and account.date_end:
            period_days = max(1, (account.date_end - account.date_start).days)
            remaining_days = max(0, (account.date_end - today).days)
        else:
            period_days = max(1, int((current.validity_days if current else 0) or 365))
            if account and account.date_end:
                remaining_days = max(0, (account.date_end - today).days)
            else:
                # No end date: treat current package as fully unused (same-day style credit).
                remaining_days = period_days

        ratio = min(1.0, float(remaining_days) / float(period_days)) if period_days else 0.0
        credit = self._money_round(current_price * ratio, currency)
        amount = self._money_round(max(0.0, target - credit), currency)

        return {
            'target': target,
            'current_price': current_price,
            'credit': credit,
            'amount': amount,
            'period_days': period_days,
            'remaining_days': remaining_days,
            'ratio': ratio,
            'currency': currency,
            'unavailable': unavailable,
            'currency_mismatch': currency_mismatch,
        }

    def _saas_upgrade_charge_amount(self):
        return self._saas_upgrade_proration()['amount']

    @api.depends(
        'requested_plan_id',
        'requested_plan_id.list_price',
        'requested_plan_id.currency_id',
        'requested_plan_id.price_label',
        'requested_plan_id.price_ids.price',
        'requested_plan_id.price_ids.currency_id',
        'current_plan_id',
        'current_plan_id.list_price',
        'current_plan_id.currency_id',
        'current_plan_id.validity_days',
        'current_plan_id.price_ids.price',
        'current_plan_id.price_ids.currency_id',
        'account_id',
        'account_id.billing_country_id',
        'account_id.date_start',
        'account_id.date_end',
        'trigger_feature',
    )
    def _compute_payment_required(self):
        setting_on = self._saas_upgrade_payment_setting_on()
        for wiz in self:
            plan = wiz.requested_plan_id
            currency = plan.currency_id if plan else self.env.company.currency_id
            free_ok = wiz._saas_plan_allows_free_request(plan) if plan else False
            details = wiz._saas_upgrade_proration() if plan and not free_ok else {
                'target': 0.0, 'credit': 0.0, 'amount': 0.0,
                'remaining_days': 0, 'period_days': 0,
                'currency': currency, 'unavailable': False, 'currency_mismatch': False,
            }
            currency = details.get('currency') or currency
            blocked = bool(details.get('unavailable') or details.get('currency_mismatch'))
            wiz.payment_required = bool(setting_on and plan and not free_ok)
            wiz.upgrade_list_price = details['target'] if wiz.payment_required and not blocked else 0.0
            wiz.upgrade_credit = details['credit'] if wiz.payment_required and not blocked else 0.0
            wiz.upgrade_amount = details['amount'] if wiz.payment_required and not blocked else 0.0
            wiz.upgrade_currency_id = currency
            if blocked and wiz.payment_required:
                wiz.upgrade_amount_label = _('Price not set for this country')
                wiz.upgrade_proration_note = wiz._regional_price_error(details)
            elif wiz.payment_required and currency and details['target'] > 0:
                wiz.upgrade_amount_label = '%s %s' % (
                    currency.symbol or currency.name or '',
                    '{:,.2f}'.format(details['amount']),
                )
                if wiz.trigger_feature == 'renewal':
                    wiz.upgrade_proration_note = _(
                        'Full package price for a new %(days)s-day term. '
                        'Unused days are not credited on renewal.'
                    ) % {'days': details['period_days']}
                else:
                    wiz.upgrade_proration_note = _(
                        'Prorated: %(new)s new plan − %(credit)s unused credit '
                        '(%(days)s of %(period)s days remaining on current package).'
                    ) % {
                        'new': '{:,.2f}'.format(details['target']),
                        'credit': '{:,.2f}'.format(details['credit']),
                        'days': details['remaining_days'],
                        'period': details['period_days'],
                    }
            elif wiz.payment_required:
                wiz.upgrade_amount_label = _('Price not set')
                wiz.upgrade_proration_note = False
            else:
                wiz.upgrade_amount_label = False
                wiz.upgrade_proration_note = False

    def action_submit(self):
        self.ensure_one()
        setting_on = self._saas_upgrade_payment_setting_on()
        free_ok = self._saas_plan_allows_free_request(self.requested_plan_id)
        if not setting_on or free_ok:
            return super().action_submit()

        details = self._saas_upgrade_proration()
        price_error = self._regional_price_error(details)
        if price_error and (details.get('unavailable') or details.get('currency_mismatch')):
            raise UserError(price_error)
        if details['target'] <= 0:
            raise UserError(_(
                'Plan "%(plan)s" has no package price. '
                'Set Package price on the SaaS plan (or turn off '
                '"Require Razorpay for SaaS plan upgrades").'
            ) % {'plan': self.requested_plan_id.name})

        # Prorated credit fully covers the new package — no Razorpay needed.
        if details['amount'] <= 0:
            return super().action_submit()

        Payment = self.env['ac.saas.upgrade.payment']
        if not Payment.saas_upgrade_payment_active():
            raise UserError(_(
                'Razorpay payment is required for plan upgrades, but API keys are not configured.\n'
                'Ask your administrator to set Razorpay keys under Settings → Razorpay Payment Gateway.'
            ))

        amount = details['amount']
        account = self.account_id
        is_manager = (
            self.env.user._is_superuser()
            or self.env.user.has_group('ac_saas_manager.group_saas_manager')
            or self.env.user.has_group('auction_module.group_auction_group_admin')
        )
        if account.user_id != self.env.user and not is_manager:
            raise UserError(_('You can only request an upgrade for your own account.'))

        Request = self.env['ac.saas.upgrade.request']
        pending = Request.sudo().search([
            ('account_id', '=', account.id),
            ('state', 'in', ('pending', 'awaiting_payment')),
            ('requested_plan_id', '=', self.requested_plan_id.id),
        ], limit=1)
        if pending:
            if pending.state == 'awaiting_payment' and pending.payment_ids:
                pay = pending.payment_ids.filtered(lambda p: p.state in ('draft', 'pending'))[:1]
                if pay:
                    vals = {
                        'amount': amount,
                        'list_price_amount': details['target'],
                        'credit_amount': details['credit'],
                        'proration_note': self.upgrade_proration_note,
                        'currency_id': details['currency'].id,
                    }
                    if (
                        abs((pay.amount or 0.0) - amount) > 0.001
                        or pay.currency_id != details['currency']
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
            raise UserError(_(
                'You already have a pending request (%(ref)s) for %(plan)s.'
            ) % {'ref': pending.name, 'plan': self.requested_plan_id.name})

        request = Request.sudo().create({
            'account_id': account.id,
            'current_plan_id': self.current_plan_id.id,
            'requested_plan_id': self.requested_plan_id.id,
            'trigger_feature': self.trigger_feature,
            'tournament_id': self.tournament_id.id if self.tournament_id else False,
            'note': self.note,
            'state': 'awaiting_payment',
            'payment_required': True,
        })
        payment = Payment.create_for_upgrade_request(
            request,
            amount=amount,
            list_price_amount=details['target'],
            credit_amount=details['credit'],
            proration_note=self.upgrade_proration_note,
            currency=details['currency'],
        )
        payment.action_create_razorpay_order()

        return {
            'type': 'ir.actions.act_url',
            'url': '/saas/upgrade/pay/%s' % payment.access_token,
            'target': 'self',
        }
