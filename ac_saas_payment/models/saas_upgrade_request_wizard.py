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

    @api.model
    def _saas_plan_allows_free_request(self, plan):
        """Only custom-quote plans (price label, no package price) skip Razorpay.

        Note: ``contact_support`` means “beyond this plan, contact support” —
        it must NOT skip payment when upgrading *to* that plan.
        """
        if not plan:
            return False
        has_price = float(plan.list_price or 0.0) > 0.0
        if has_price:
            return False
        # No numeric price + marketing override like “Contact us”
        if (plan.price_label or '').strip():
            return True
        return False

    def _saas_upgrade_proration(self):
        """Prorated upgrade: new package price minus unused credit on current package.

        credit = current_list_price × (remaining_days / period_days)
        amount = max(0, new_list_price − credit)

        Same-day upgrade with full remaining validity ≈ new − current (not both full prices).
        Expired / no remaining days → credit 0 → full new package price.
        """
        self.ensure_one()
        plan = self.requested_plan_id
        current = self.current_plan_id
        account = self.account_id
        target = float(plan.list_price or 0.0) if plan else 0.0
        current_price = float(current.list_price or 0.0) if current else 0.0

        today = fields.Date.context_today(self)
        period_days = 0
        remaining_days = 0

        if self.trigger_feature == 'renewal':
            period_days = max(1, int((plan.validity_days if plan else 0) or 365))
            return {
                'target': target,
                'current_price': current_price,
                'credit': 0.0,
                'amount': round(target, 2),
                'period_days': period_days,
                'remaining_days': 0,
                'ratio': 0.0,
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
        credit = round(current_price * ratio, 2)
        amount = round(max(0.0, target - credit), 2)

        return {
            'target': target,
            'current_price': current_price,
            'credit': credit,
            'amount': amount,
            'period_days': period_days,
            'remaining_days': remaining_days,
            'ratio': ratio,
        }

    def _saas_upgrade_charge_amount(self):
        return self._saas_upgrade_proration()['amount']

    @api.depends(
        'requested_plan_id',
        'requested_plan_id.list_price',
        'requested_plan_id.currency_id',
        'requested_plan_id.price_label',
        'current_plan_id',
        'current_plan_id.list_price',
        'current_plan_id.validity_days',
        'account_id',
        'account_id.date_start',
        'account_id.date_end',
        'trigger_feature',
    )
    def _compute_payment_required(self):
        setting_on = self._saas_upgrade_payment_setting_on()
        for wiz in self:
            plan = wiz.requested_plan_id
            currency = plan.currency_id if plan else self.env.company.currency_id
            free_ok = wiz._saas_plan_allows_free_request(plan)
            details = wiz._saas_upgrade_proration() if plan and not free_ok else {
                'target': 0.0, 'credit': 0.0, 'amount': 0.0,
                'remaining_days': 0, 'period_days': 0,
            }
            wiz.payment_required = bool(setting_on and plan and not free_ok)
            wiz.upgrade_list_price = details['target'] if wiz.payment_required else 0.0
            wiz.upgrade_credit = details['credit'] if wiz.payment_required else 0.0
            wiz.upgrade_amount = details['amount'] if wiz.payment_required else 0.0
            wiz.upgrade_currency_id = currency
            if wiz.payment_required and currency and details['target'] > 0:
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
                    }
                    if abs((pay.amount or 0.0) - amount) > 0.001:
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
        )
        payment.action_create_razorpay_order()

        return {
            'type': 'ir.actions.act_url',
            'url': '/saas/upgrade/pay/%s' % payment.access_token,
            'target': 'self',
        }
