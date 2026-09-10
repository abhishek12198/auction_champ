# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — Plan upgrade requests (manual ops)
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AcSaasUpgradeRequest(models.Model):
    _name = 'ac.saas.upgrade.request'
    _description = 'SaaS Plan Upgrade Request'
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending',
        required=True,
        index=True,
    )
    account_id = fields.Many2one(
        'ac.saas.account',
        string='Account',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Requested By',
        related='account_id.user_id',
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        related='account_id.partner_id',
        store=True,
        readonly=True,
    )
    current_plan_id = fields.Many2one(
        'ac.saas.plan',
        string='Current Plan',
        required=True,
        ondelete='restrict',
    )
    requested_plan_id = fields.Many2one(
        'ac.saas.plan',
        string='Requested Plan',
        required=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
    )
    trigger_feature = fields.Selection(
        [
            ('theme', 'Player card theme'),
            ('random', 'Random mode'),
            ('teams', 'More teams'),
            ('players', 'More players'),
            ('tournaments', 'More tournaments'),
            ('parallel', 'Parallel tournaments (multi-device)'),
            ('renewal', 'Account renewal / reactivation'),
            ('other', 'Other'),
        ],
        string='Looking for',
        required=True,
        default='other',
    )
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        ondelete='set null',
    )
    note = fields.Text(string='Customer note')
    admin_note = fields.Text(string='Internal note')
    date_requested = fields.Datetime(
        string='Requested On',
        default=fields.Datetime.now,
        readonly=True,
    )
    date_processed = fields.Datetime(string='Processed On', readonly=True)
    processed_by_id = fields.Many2one(
        'res.users',
        string='Processed By',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        Seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = Seq.next_by_code('ac.saas.upgrade.request') or _('New')
        return super().create(vals_list)

    @api.constrains('current_plan_id', 'requested_plan_id', 'trigger_feature')
    def _check_requested_plan_higher(self):
        for rec in self:
            if rec.trigger_feature == 'renewal':
                continue
            if (
                rec.current_plan_id
                and rec.requested_plan_id
                and rec.requested_plan_id.sequence <= rec.current_plan_id.sequence
            ):
                raise ValidationError(_(
                    'Please choose a plan higher than %(plan)s.'
                ) % {'plan': rec.current_plan_id.name})

    def action_cancel(self):
        for rec in self:
            if not rec._saas_user_owns_request() and not rec._saas_is_manager():
                raise AccessError(_('You can only cancel your own upgrade requests.'))
            if rec.state != 'pending':
                raise UserError(_('Only pending requests can be cancelled.'))
            rec.sudo().write({'state': 'cancelled'})
        return True

    def action_approve(self):
        self._saas_require_manager()
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only pending requests can be approved.'))
            account = rec.account_id.sudo()
            if rec.trigger_feature == 'renewal' or account.state == 'expired' or account._is_frozen():
                vals = account._vals_for_renewed_term(plan=rec.requested_plan_id)
            else:
                vals = {'plan_id': rec.requested_plan_id.id}
            account.with_context(saas_skip_freeze=True).write(vals)
            rec.write({
                'state': 'approved',
                'date_processed': fields.Datetime.now(),
                'processed_by_id': self.env.user.id,
            })
            rec._notify_customer_processed(approved=True)
        return True

    def action_reject(self):
        self._saas_require_manager()
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only pending requests can be rejected.'))
            rec.write({
                'state': 'rejected',
                'date_processed': fields.Datetime.now(),
                'processed_by_id': self.env.user.id,
            })
            rec._notify_customer_processed(approved=False)
        return True

    def _saas_is_manager(self):
        user = self.env.user
        return (
            user.has_group('ac_saas_manager.group_saas_manager')
            or user.has_group('auction_module.group_auction_group_admin')
            or user._is_superuser()
        )

    def _saas_user_owns_request(self):
        self.ensure_one()
        return self.account_id.user_id == self.env.user

    def _saas_require_manager(self):
        if not self._saas_is_manager():
            raise AccessError(_('Only SaaS managers can process upgrade requests.'))

    def _manager_partners(self):
        group = self.env.ref('ac_saas_manager.group_saas_manager', raise_if_not_found=False)
        if not group:
            return self.env['res.partner']
        return group.users.mapped('partner_id').filtered(lambda p: p.email)

    def _notify_managers_new_request(self):
        """Email SaaS managers about a new pending request (best-effort)."""
        if 'mail.mail' not in self.env:
            return
        Mail = self.env['mail.mail']
        partners = self._manager_partners()
        if not partners:
            return
        for rec in self:
            body = _(
                '<p>New plan upgrade request <strong>%(ref)s</strong>.</p>'
                '<ul>'
                '<li>Account: %(account)s</li>'
                '<li>User: %(user)s</li>'
                '<li>Current plan: %(current)s</li>'
                '<li>Requested plan: %(requested)s</li>'
                '<li>Looking for: %(feature)s</li>'
                '<li>Note: %(note)s</li>'
                '</ul>'
                '<p>Open SaaS → Upgrade Requests to approve or reject.</p>'
            ) % {
                'ref': rec.name,
                'account': rec.account_id.name,
                'user': rec.user_id.name,
                'current': rec.current_plan_id.name,
                'requested': rec.requested_plan_id.name,
                'feature': dict(rec._fields['trigger_feature'].selection).get(
                    rec.trigger_feature, rec.trigger_feature),
                'note': rec.note or '—',
            }
            for partner in partners:
                mail = Mail.sudo().create({
                    'subject': _('AuctionChamp upgrade request: %(ref)s (%(plan)s)') % {
                        'ref': rec.name,
                        'plan': rec.requested_plan_id.name,
                    },
                    'body_html': body,
                    'email_from': self.env['ac.saas.account']._saas_email_from(),
                    'email_to': partner.email,
                    'auto_delete': True,
                })
                mail.send()

    def _notify_customer_processed(self, approved=True):
        if 'mail.mail' not in self.env:
            return
        Mail = self.env['mail.mail']
        for rec in self:
            email = rec.partner_id.email or rec.user_id.email
            if not email:
                continue
            if approved:
                if rec.trigger_feature == 'renewal':
                    subject = _('Your AuctionChamp plan has been renewed')
                    body = _(
                        '<p>Hi %(name)s,</p>'
                        '<p>Your plan renewal <strong>%(ref)s</strong> is complete.</p>'
                        '<p>Your account is active again on the <strong>%(plan)s</strong> plan. '
                        'You can create tournaments for this new term after you refresh the app.</p>'
                    ) % {
                        'name': rec.user_id.name,
                        'ref': rec.name,
                        'plan': rec.requested_plan_id.name,
                    }
                else:
                    subject = _('Your AuctionChamp plan is now %(plan)s') % {
                        'plan': rec.requested_plan_id.name,
                    }
                    body = _(
                        '<p>Hi %(name)s,</p>'
                        '<p>Your upgrade request <strong>%(ref)s</strong> was approved.</p>'
                        '<p>Your account is now on the <strong>%(plan)s</strong> plan. '
                        'New features are available after you refresh the app.</p>'
                    ) % {
                        'name': rec.user_id.name,
                        'ref': rec.name,
                        'plan': rec.requested_plan_id.name,
                    }
            else:
                subject = _('Update on your AuctionChamp upgrade request')
                body = _(
                    '<p>Hi %(name)s,</p>'
                    '<p>Your upgrade request <strong>%(ref)s</strong> '
                    'for <strong>%(plan)s</strong> was not approved at this time.</p>'
                    '<p>Please contact support if you have questions.</p>'
                ) % {
                    'name': rec.user_id.name,
                    'ref': rec.name,
                    'plan': rec.requested_plan_id.name,
                }
            mail = Mail.sudo().create({
                'subject': subject,
                'body_html': body,
                'email_from': self.env['ac.saas.account']._saas_email_from(),
                'email_to': email,
                'auto_delete': True,
            })
            mail.send()
