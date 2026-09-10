# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AcSaasUpgradeRequest(models.Model):
    _inherit = 'ac.saas.upgrade.request'

    state = fields.Selection(
        selection_add=[
            ('awaiting_payment', 'Awaiting Payment'),
        ],
        ondelete={'awaiting_payment': 'set default'},
    )
    payment_required = fields.Boolean(
        string='Payment required',
        default=False,
        help='Set when this request was created under paid-upgrade mode.',
    )
    payment_ids = fields.One2many(
        'ac.saas.upgrade.payment',
        'upgrade_request_id',
        string='Payments',
    )
    payment_amount = fields.Monetary(
        string='Paid amount',
        currency_field='payment_currency_id',
        compute='_compute_payment_info',
        store=True,
    )
    payment_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_payment_info',
        store=True,
    )
    razorpay_payment_id = fields.Char(
        string='Razorpay Payment ID',
        compute='_compute_payment_info',
        store=True,
    )

    @api.depends(
        'payment_ids.state',
        'payment_ids.amount',
        'payment_ids.currency_id',
        'payment_ids.razorpay_payment_id',
    )
    def _compute_payment_info(self):
        for rec in self:
            paid = rec.payment_ids.filtered(lambda p: p.state == 'paid')[:1]
            rec.payment_amount = paid.amount if paid else 0.0
            rec.payment_currency_id = paid.currency_id if paid else False
            rec.razorpay_payment_id = paid.razorpay_payment_id if paid else False

    def action_cancel(self):
        awaiting = self.filtered(lambda r: r.state == 'awaiting_payment')
        others = self - awaiting
        for rec in awaiting:
            if not rec._saas_user_owns_request() and not rec._saas_is_manager():
                from odoo.exceptions import AccessError
                raise AccessError(_('You can only cancel your own upgrade requests.'))
            rec.sudo().write({'state': 'cancelled'})
            rec.payment_ids.filtered(lambda p: p.state in ('draft', 'pending')).write({
                'state': 'cancelled',
            })
        if others:
            return super(AcSaasUpgradeRequest, others).action_cancel()
        return True

    def action_approve(self):
        """Block manual approve for unpaid awaiting_payment rows."""
        for rec in self:
            if rec.state == 'awaiting_payment':
                raise UserError(_(
                    'This request is awaiting Razorpay payment. '
                    'It will upgrade automatically after payment, '
                    'or cancel it and ask the customer to retry.'
                ))
        return super().action_approve()

    def _saas_apply_paid_upgrade(self, payment=None):
        """Apply plan change after successful Razorpay payment (auto-approve)."""
        self.ensure_one()
        if self.state == 'approved':
            return True
        if self.state not in ('awaiting_payment', 'pending'):
            raise UserError(_('This upgrade request cannot be completed from payment.'))

        account = self.account_id.sudo()
        if self.trigger_feature == 'renewal' or account.state == 'expired' or account._is_frozen():
            vals = account._vals_for_renewed_term(plan=self.requested_plan_id)
        else:
            vals = {'plan_id': self.requested_plan_id.id}
        account.with_context(saas_skip_freeze=True).write(vals)
        note = self.admin_note or ''
        pay_note = ''
        if payment:
            pay_note = _('Paid via Razorpay (%s).') % (payment.razorpay_payment_id or payment.name)
        self.sudo().write({
            'state': 'approved',
            'date_processed': fields.Datetime.now(),
            'processed_by_id': self.env.user.id if not self.env.user._is_public() else False,
            'admin_note': ((note + '\n') if note else '') + pay_note if pay_note else note,
            'payment_required': True,
        })
        self._notify_customer_processed(approved=True)
        self._notify_managers_paid_upgrade(payment=payment)
        return True

    def _notify_managers_paid_upgrade(self, payment=None):
        if 'mail.mail' not in self.env:
            return
        Mail = self.env['mail.mail']
        partners = self._manager_partners()
        if not partners:
            return
        for rec in self:
            body = _(
                '<p>Paid plan upgrade completed: <strong>%(ref)s</strong>.</p>'
                '<ul>'
                '<li>Account: %(account)s</li>'
                '<li>User: %(user)s</li>'
                '<li>New plan: %(plan)s</li>'
                '<li>Amount: %(amount)s</li>'
                '<li>Razorpay: %(rzp)s</li>'
                '</ul>'
            ) % {
                'ref': rec.name,
                'account': rec.account_id.name,
                'user': rec.user_id.name,
                'plan': rec.requested_plan_id.name,
                'amount': ('%s %s' % (
                    payment.currency_id.name if payment else '',
                    payment.amount if payment else rec.payment_amount or '',
                )).strip() or '—',
                'rzp': (payment.razorpay_payment_id if payment else rec.razorpay_payment_id) or '—',
            }
            for partner in partners:
                mail = Mail.sudo().create({
                    'subject': _('Paid SaaS upgrade: %(ref)s → %(plan)s') % {
                        'ref': rec.name,
                        'plan': rec.requested_plan_id.name,
                    },
                    'body_html': body,
                    'email_from': self.env['ac.saas.account']._saas_email_from(),
                    'email_to': partner.email,
                    'auto_delete': True,
                })
                mail.send()
