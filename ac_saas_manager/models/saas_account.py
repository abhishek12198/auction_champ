# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — One account = one login
#
##############################################################################
import base64
import ipaddress
import logging
import os
import secrets
import string
from datetime import timedelta
from email.utils import make_msgid
from html import escape as html_escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import formataddr

_logger = logging.getLogger(__name__)

_SAAS_MONTHS = (
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)
SAAS_SUPPORT_EMAIL = 'auctionchamp.live@gmail.com'
SAAS_SUPPORT_PHONE_DISPLAY = '+91 79940 64448'
SAAS_SUPPORT_PHONE_TEL = '+917994064448'
SAAS_SUPPORT_WHATSAPP = '917994064448'
SAAS_PUBLIC_SITE = 'https://www.auctionchamp.live'
SAAS_WELCOME_SUBJECT = 'Auction Champ™ | Your Complete Welcome & Setup Guide'


class AcSaasAccount(models.Model):
    _name = 'ac.saas.account'
    _description = 'AuctionChamp SaaS Account'
    _order = 'name, id'

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('expired', 'Expired'),
        ],
        default='active',
        required=True,
        index=True,
    )
    # One account ↔ one login user
    user_id = fields.Many2one(
        'res.users',
        string='Login User',
        required=True,
        ondelete='restrict',
        index=True,
        help='The single user account that logs in for this SaaS customer.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        related='user_id.partner_id',
        store=True,
        readonly=True,
    )
    plan_id = fields.Many2one(
        'ac.saas.plan',
        string='Plan',
        required=True,
        ondelete='restrict',
        index=True,
    )
    date_start = fields.Date(string='Start Date', default=fields.Date.context_today)
    date_end = fields.Date(string='End Date')
    notes = fields.Text()

    tournament_ids = fields.One2many(
        'auction.tournament',
        'saas_account_id',
        string='Tournaments',
    )
    tournament_count = fields.Integer(compute='_compute_usage')
    team_count = fields.Integer(compute='_compute_usage')
    player_count = fields.Integer(compute='_compute_usage')

    # Plan quota (related). Create cap after renewals is tournament_create_limit.
    max_tournaments = fields.Integer(related='plan_id.max_tournaments', readonly=True)
    tournament_create_limit = fields.Integer(
        compute='_compute_tournament_create_limit',
        string='Tournament slots',
        help='Tournaments this account may create (plan quota × packages purchased).',
    )
    max_teams_per_tournament = fields.Integer(
        related='plan_id.max_teams_per_tournament', readonly=True)
    max_players_per_tournament = fields.Integer(
        related='plan_id.max_players_per_tournament', readonly=True)
    allow_auctioneer_console = fields.Boolean(
        related='plan_id.allow_auctioneer_console',
        readonly=True,
        string='Auctioneer Console (from plan)',
    )
    allow_pool_creator = fields.Boolean(
        related='plan_id.allow_pool_creator',
        readonly=True,
        string='Pool Creator (from plan)',
    )
    allow_parallel_sessions = fields.Boolean(
        related='plan_id.allow_parallel_sessions',
        readonly=True,
        string='Plan: parallel sessions',
    )
    disable_parallel_sessions = fields.Boolean(
        string='Disable parallel sessions',
        default=False,
        help='Force a single shared working tournament for this account on all devices, '
             'even when the plan allows parallel sessions. '
             'Leave unchecked to use the plan default.',
    )

    _sql_constraints = [
        ('user_uniq', 'unique(user_id)',
         'Each login user can belong to only one SaaS account.'),
    ]

    @api.depends('plan_id', 'plan_id.max_tournaments')
    def _compute_tournament_create_limit(self):
        for acc in self:
            acc.tournament_create_limit = acc._effective_tournament_limit()

    @api.depends('tournament_ids', 'tournament_ids.team_ids', 'plan_id')
    def _compute_usage(self):
        Player = self.env['auction.team.player'].sudo()
        for acc in self:
            tournaments = acc.tournament_ids
            acc.tournament_count = len(tournaments)
            acc.team_count = sum(len(t.team_ids) for t in tournaments)
            if tournaments:
                acc.player_count = Player.search_count([
                    ('tournament_id', 'in', tournaments.ids),
                    ('icon_player', '=', False),
                ])
            else:
                acc.player_count = 0

    @api.model
    def _get_account_for_user(self, user=None):
        """Return the SaaS account for a login user (or False)."""
        user = user or self.env.user
        if user._is_superuser() or user.has_group('base.group_system'):
            return self.browse()
        if user.has_group('auction_module.group_auction_group_admin'):
            return self.browse()
        return self.sudo().search([('user_id', '=', user.id)], limit=1)

    def _ensure_active(self):
        self.ensure_one()
        self._sync_expiry_from_date()
        if self.state != 'active' or not self.active:
            raise AccessError(_(
                'Your AuctionChamp account "%(name)s" is %(state)s. '
                'Renew your plan to continue.'
            ) % {
                'name': self.name,
                'state': dict(self._fields['state'].selection).get(self.state, self.state),
            })

    def _is_frozen(self):
        """Expired (or past end date) accounts are frozen: read-only + renew only."""
        self.ensure_one()
        if self.state == 'expired':
            return True
        if (
            self.state == 'active'
            and self.date_end
            and self.date_end < fields.Date.context_today(self)
        ):
            return True
        return False

    def _sync_expiry_from_date(self):
        """Flip active → expired when End Date has passed."""
        today = fields.Date.context_today(self)
        to_expire = self.filtered(
            lambda a: a.state == 'active' and a.date_end and a.date_end < today
        )
        if to_expire:
            # Keep login enabled for expired users (unlike suspended).
            to_expire.with_context(saas_skip_freeze=True).write({'state': 'expired'})

    @api.model
    def _cron_expire_accounts(self):
        today = fields.Date.context_today(self)
        accounts = self.search([
            ('state', '=', 'active'),
            ('date_end', '!=', False),
            ('date_end', '<', today),
        ])
        if accounts:
            accounts.with_context(saas_skip_freeze=True).write({'state': 'expired'})
        return True

    def assert_not_frozen(self, operation='change data'):
        """Block mutations for expired / past-end-date accounts."""
        for acc in self:
            acc._sync_expiry_from_date()
            if acc._is_frozen():
                raise AccessError(_(
                    'Your AuctionChamp account "%(name)s" has expired and is frozen. '
                    'You cannot %(op)s until it is renewed. '
                    'Use "Renew plan" in the top bar to pay and restore access.'
                ) % {'name': acc.name, 'op': operation})

    @api.model
    def assert_env_not_frozen(self, operation='change data'):
        """Raise if the current login's SaaS account is frozen."""
        if self.env.context.get('saas_skip_freeze'):
            return
        user = self.env.user
        if (
            self.env.su
            or user._is_superuser()
            or user.has_group('base.group_system')
            or user.has_group('auction_module.group_auction_group_admin')
            or user.has_group('ac_saas_manager.group_saas_manager')
        ):
            return
        account = self._get_account_for_user(user)
        if account:
            account.assert_not_frozen(operation=operation)

    @api.model
    def assert_tournament_not_frozen(self, tournament, operation='change data'):
        """Raise if the tournament's owning SaaS account is frozen (incl. public/sudo)."""
        if self.env.context.get('saas_skip_freeze') or not tournament:
            return
        account = tournament.sudo().saas_account_id
        if account:
            account.assert_not_frozen(operation=operation)

    def action_activate(self):
        """Activate a draft / expired account and restore login access."""
        for acc in self:
            if acc.state not in ('draft', 'expired', 'suspended'):
                raise UserError(_(
                    'Account "%s" cannot be activated from state "%s".'
                ) % (acc.name, acc.state))
        self.write({'state': 'active', 'active': True})
        return True

    def action_suspend(self):
        """Suspend the account immediately — linked user cannot log in."""
        for acc in self:
            if acc.state == 'suspended':
                continue
            if not acc.user_id:
                raise UserError(_(
                    'Account "%s" has no login user to suspend.'
                ) % acc.name)
            if acc.user_id._is_superuser() or acc.user_id.has_group('base.group_system'):
                raise UserError(_(
                    'Refusing to suspend account "%s": the login user is a system administrator.'
                ) % acc.name)
        to_suspend = self.filtered(lambda a: a.state != 'suspended')
        if to_suspend:
            to_suspend.write({'state': 'suspended'})
        return True

    def action_reactivate(self):
        """Reactivate a suspended account and restore login access."""
        for acc in self:
            if acc.state != 'suspended':
                raise UserError(_(
                    'Only suspended accounts can be reactivated (account "%s" is %s).'
                ) % (acc.name, acc.state))
        self.write({'state': 'active', 'active': True})
        return True

    def _is_nearing_expiry(self, days=10):
        """True when End Date is within ``days`` (inclusive) and account is still active."""
        self.ensure_one()
        if self.state != 'active' or not self.date_end:
            return False
        today = fields.Date.context_today(self)
        days_left = (self.date_end - today).days
        return 0 <= days_left <= days

    def _can_request_renewal(self):
        """Renewal request allowed in the 10-day warning window or when frozen/expired."""
        self.ensure_one()
        self._sync_expiry_from_date()
        return self._is_frozen() or self.state == 'expired' or self._is_nearing_expiry(10)

    def _assert_can_request_renewal(self):
        """Raise if this login cannot start a same-plan renewal."""
        self.ensure_one()
        if (
            self.user_id != self.env.user
            and not self.env.user._is_superuser()
            and not self.env.user.has_group('ac_saas_manager.group_saas_manager')
            and not self.env.user.has_group('auction_module.group_auction_group_admin')
        ):
            raise UserError(_('You can only request reactivation for your own account.'))

        self._sync_expiry_from_date()
        if not self._can_request_renewal():
            raise UserError(_(
                'Renewal can be requested within 10 days of your End Date, '
                'or after the account has expired (account "%s").'
            ) % self.name)

    def _vals_for_renewed_term(self, plan=None):
        """Start a new package term from the purchase date.

        ``date_start`` is today (payment / approval day).
        ``date_end`` is today plus the plan's validity (usually 365 days).
        Leftover days from the previous term are not carried forward.
        """
        self.ensure_one()
        plan = plan or self.plan_id
        today = fields.Date.context_today(self)
        validity = int((plan.validity_days if plan else 0) or 365)
        return {
            'state': 'active',
            'active': True,
            'plan_id': plan.id if plan else False,
            'date_start': today,
            'date_end': today + timedelta(days=validity),
        }

    def _approved_renewal_count(self):
        """How many extra packages were added after the original signup."""
        self.ensure_one()
        if not isinstance(self.id, int):
            return 0
        domain = [
            ('account_id', '=', self.id),
            ('state', '=', 'approved'),
            ('trigger_feature', '=', 'renewal'),
        ]
        # Same-plan paid/approved rows that were not tagged as renewal still count.
        if self.plan_id:
            domain = [
                ('account_id', '=', self.id),
                ('state', '=', 'approved'),
                '|',
                ('trigger_feature', '=', 'renewal'),
                '&',
                ('current_plan_id', '=', self.plan_id.id),
                ('requested_plan_id', '=', self.plan_id.id),
            ]
        return self.env['ac.saas.upgrade.request'].sudo().search_count(domain)

    def _effective_tournament_limit(self):
        """Total tournaments this account may create.

        Signup grants one package (``plan.max_tournaments``). Each approved
        renewal buys another package of the same size, so an existing
        tournament from a previous purchase does not block the new one.
        """
        self.ensure_one()
        plan_max = int(self.plan_id.max_tournaments or 0) if self.plan_id else 0
        if not plan_max:
            return 0
        return plan_max * (1 + self._approved_renewal_count())

    def _tournament_count_for_quota(self):
        self.ensure_one()
        return self.env['auction.tournament'].sudo().search_count([
            ('saas_account_id', '=', self.id),
        ])

    def _renewal_customer_note(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.date_end:
            days_left = (self.date_end - today).days
            if self._is_frozen() or days_left < 0:
                return _(
                    'Account expired on %(date)s — please renew / reactivate.'
                ) % {'date': self.date_end}
            return _(
                'Account is expiring on %(date)s (%(days)s day(s) left) — '
                'please renew / reactivate.'
            ) % {'date': self.date_end, 'days': days_left}
        return _('Please renew / reactivate this account.')

    def action_request_reactivation(self):
        """Customer action: request renewal during the 10-day window or after expiry."""
        self.ensure_one()
        self._assert_can_request_renewal()

        Request = self.env['ac.saas.upgrade.request'].sudo()
        pending = Request.search([
            ('account_id', '=', self.id),
            ('state', '=', 'pending'),
            ('trigger_feature', '=', 'renewal'),
        ], limit=1)
        if pending:
            raise UserError(_(
                'You already have a pending reactivation request (%(ref)s). '
                'We will confirm it shortly.'
            ) % {'ref': pending.name})

        note = self._renewal_customer_note()

        request = Request.create({
            'account_id': self.id,
            'current_plan_id': self.plan_id.id,
            'requested_plan_id': self.plan_id.id,
            'trigger_feature': 'renewal',
            'note': note,
            'state': 'pending',
        })
        request._notify_managers_new_request()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reactivation requested'),
                'message': _(
                    'Request %(ref)s was submitted. Support will renew your account shortly.'
                ) % {'ref': request.name},
                'type': 'success',
                'sticky': False,
            },
        }

    def _apply_login_access(self):
        """Archive / unarchive the linked login user to match account state.

        Suspended → no login.
        Active / Expired → login allowed (expired is frozen but can request renew).
        """
        for acc in self:
            user = acc.user_id
            if not user:
                continue
            user = user.sudo().with_context(active_test=False)
            if user._is_superuser() or user.has_group('base.group_system'):
                continue
            allow_login = bool(acc.active and acc.state in ('active', 'expired'))
            if user.active != allow_login:
                user.with_context(no_reset_password=True).write({'active': allow_login})

    def get_plan(self):
        self.ensure_one()
        self._ensure_active()
        if not self.plan_id:
            raise UserError(_('No SaaS plan is assigned to this account.'))
        return self.plan_id

    def parallel_sessions_effective(self):
        """Per-browser working tournament when plan allows and not opted out."""
        self.ensure_one()
        plan = self.plan_id
        if not plan or not plan.allow_parallel_sessions:
            return False
        return not self.disable_parallel_sessions

    def assert_can_create_tournament(self):
        self.ensure_one()
        plan = self.get_plan()
        current = self._tournament_count_for_quota()
        limit = self._effective_tournament_limit()
        if current >= limit:
            raise ValidationError(_(
                'Your %(plan)s plan allows %(max)s tournament(s) for the packages '
                'you have purchased (%(pkg)s per package). You already have %(cur)s. '
                'Renew the same plan to add another %(pkg)s, or upgrade to a higher plan.'
            ) % {
                'plan': plan.name,
                'max': limit,
                'pkg': plan.max_tournaments,
                'cur': current,
            })

    def assert_can_add_team(self, tournament):
        self.ensure_one()
        plan = self.get_plan()
        # Count only this tournament's teams (not account-wide)
        current = self.env['auction.team'].sudo().search_count([
            ('tournament_id', '=', tournament.id),
        ])
        if current >= plan.max_teams_per_tournament:
            raise ValidationError(_(
                'Your %(plan)s plan allows up to %(max)s team(s) per tournament. '
                '"%(tournament)s" already has %(cur)s. '
                'Switch to another tournament or upgrade your plan.'
            ) % {
                'plan': plan.name,
                'max': plan.max_teams_per_tournament,
                'tournament': tournament.name,
                'cur': current,
            })

    def assert_can_add_player(self, tournament):
        self.ensure_one()
        plan = self.get_plan()
        current = self.env['auction.team.player'].sudo().search_count([
            ('tournament_id', '=', tournament.id),
            ('icon_player', '=', False),
        ])
        if current >= plan.max_players_per_tournament:
            raise ValidationError(_(
                'Your %(plan)s plan allows up to %(max)s player registration(s) '
                'per tournament. "%(tournament)s" already has %(cur)s. '
                'Upgrade your plan or contact support.'
            ) % {
                'plan': plan.name,
                'max': plan.max_players_per_tournament,
                'tournament': tournament.name,
                'cur': current,
            })

    def action_open_tournaments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tournaments'),
            'res_model': 'auction.tournament',
            'view_mode': 'kanban,tree,form',
            'domain': [('saas_account_id', '=', self.id)],
            'context': {'default_saas_account_id': self.id},
        }

    def action_open_upgrade_wizard(self, trigger_feature='other', tournament_id=False):
        """Open the plan-upgrade request wizard for this account."""
        self.ensure_one()
        if (
            self.user_id != self.env.user
            and not self.env.user._is_superuser()
            and not self.env.user.has_group('ac_saas_manager.group_saas_manager')
            and not self.env.user.has_group('auction_module.group_auction_group_admin')
        ):
            raise UserError(_('You can only request an upgrade for your own account.'))

        plan = self.plan_id
        if not plan:
            raise UserError(_('No plan is assigned to this account.'))

        higher = self.env['ac.saas.plan'].search([
            ('active', '=', True),
            ('sequence', '>', plan.sequence),
        ], order='sequence, id', limit=1)
        if not higher:
            raise UserError(_(
                'You are already on the highest available plan. Contact support for custom needs.'
            ))

        suggested = higher
        if trigger_feature == 'random':
            suggested = self.env['ac.saas.plan'].get_min_plan_for_random() or higher
        elif trigger_feature == 'parallel':
            suggested = (
                self.env['ac.saas.plan'].get_min_plan_for_parallel_sessions() or higher
            )

        ctx = {
            'default_requested_plan_id': suggested.id,
            'default_trigger_feature': trigger_feature or 'other',
            'default_tournament_id': tournament_id or False,
            # Odoo ActionDialog reads dialog_size from context (not flags).
            'dialog_size': 'medium',
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Request plan upgrade'),
            'res_model': 'ac.saas.upgrade.request.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': ctx,
        }

    @api.model
    def _saas_login_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return '%s/web/login' % base.rstrip('/')

    @api.model
    def _saas_mail_server(self):
        return self.env['ir.mail_server'].sudo().search([], order='sequence,id', limit=1)

    @api.model
    def _saas_from_is_unroutable(self, email_from):
        """True when From would bounce (laptop host, missing domain)."""
        raw = (email_from or '').strip()
        if not raw or '@' not in raw:
            return True
        domain = raw.rsplit('@', 1)[-1].strip('> ').lower()
        if not domain or '.' not in domain:
            return True
        if 'localhost' in domain or domain.endswith('.local') or domain.endswith('.lan'):
            return True
        return False

    @api.model
    def _saas_sender_address(self):
        """Bare mailbox used as SMTP From (must match the outgoing server login)."""
        server = self._saas_mail_server()
        smtp_user = (server.smtp_user or '').strip() if server else ''
        if smtp_user and '@' in smtp_user and not self._saas_from_is_unroutable(smtp_user):
            return smtp_user
        from_filter = (getattr(server, 'from_filter', None) or '').strip() if server else ''
        if from_filter and '@' in from_filter and not self._saas_from_is_unroutable(from_filter):
            return from_filter.split(',')[0].strip()

        ICP = self.env['ir.config_parameter'].sudo()
        default_from = (ICP.get_param('mail.default.from') or '').strip()
        catchall = (ICP.get_param('mail.catchall.domain') or '').strip()
        if default_from and '@' in default_from and not self._saas_from_is_unroutable(default_from):
            return default_from
        if default_from and catchall:
            combined = '%s@%s' % (default_from, catchall)
            if not self._saas_from_is_unroutable(combined):
                return combined

        company = self.env.company.sudo()
        if company.email and '@' in company.email and not self._saas_from_is_unroutable(company.email):
            return company.email.strip()

        return 'noreply@auctionchamp.live'

    @api.model
    def _saas_mail_domain(self):
        addr = self._saas_sender_address()
        return addr.rsplit('@', 1)[-1].strip().lower()

    @api.model
    def _saas_message_id(self):
        return make_msgid(domain=self._saas_mail_domain())

    @api.model
    def _saas_message_id_is_unroutable(self, message_id):
        raw = (message_id or '').strip()
        if not raw or '@' not in raw:
            return True
        host = raw.rsplit('@', 1)[-1].rstrip('>').lower()
        return self._saas_from_is_unroutable('noreply@%s' % host)

    @api.model
    def _saas_email_from(self):
        """From header: AuctionChamp <smtp-mailbox@domain>."""
        addr = self._saas_sender_address()
        try:
            return formataddr(('AuctionChamp', addr))
        except Exception:
            return addr

    @api.model
    def _saas_ensure_mail_default_from(self):
        """So Odoo does not fall back to a laptop hostname for later mails."""
        ICP = self.env['ir.config_parameter'].sudo()
        current = (ICP.get_param('mail.default.from') or '').strip()
        if current and not self._saas_from_is_unroutable(current):
            return
        ICP.set_param('mail.default.from', self._saas_sender_address())

    @api.model
    def _generate_temp_password(self, length=12):
        alphabet = string.ascii_letters + string.digits
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
        ]
        chars += [secrets.choice(alphabet) for _ in range(max(0, length - 3))]
        secrets.SystemRandom().shuffle(chars)
        return ''.join(chars)

    @api.model
    def _saas_format_date(self, value):
        if not value:
            return '—'
        if isinstance(value, str):
            value = fields.Date.to_date(value)
        return '%d %s %d' % (value.day, _SAAS_MONTHS[value.month], value.year)

    @api.model
    def _saas_public_base_url(self):
        """Customer-facing origin. A laptop or LAN base URL is not used in mail."""
        raw = (
            self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        ).strip().rstrip('/')
        if not raw.startswith('https://'):
            return SAAS_PUBLIC_SITE
        host = raw.split('://', 1)[1].split('/')[0].split(':')[0].strip('[]').lower()
        if not host or host == 'localhost' or host.endswith('.local') or host.endswith('.lan'):
            return SAAS_PUBLIC_SITE
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip and (ip.is_private or ip.is_loopback or ip.is_link_local):
            return SAAS_PUBLIC_SITE
        return raw

    @api.model
    def _saas_welcome_email_html(
        self, name, plan, account, valid_until, login, password,
        invoice_attached, login_url, manual_url,
    ):
        """Welcome letter sent after a subscription. Values are escaped here."""
        e = html_escape
        login_href = e(login_url or '', quote=True)
        manual_href = e(manual_url or '', quote=True)
        mailto = 'mailto:%s' % SAAS_SUPPORT_EMAIL
        wa_href = 'https://wa.me/%s' % SAAS_SUPPORT_WHATSAPP
        tel_href = 'tel:%s' % SAAS_SUPPORT_PHONE_TEL

        if invoice_attached:
            payment_note = (
                '<p style="margin:0 0 14px;">We&rsquo;re pleased to confirm that your '
                'payment has been received successfully. Your invoice is attached to '
                'this email for your reference.</p>'
            )
        else:
            payment_note = ''

        rows = (
            ('Plan', '<strong>%s</strong>' % e(plan or '—')),
            ('Account Name', e(account or '—')),
            ('Valid Until', e(valid_until or '—')),
            (
                'Login Portal',
                '<a href="%s" style="color:#1565c0;text-decoration:none;">'
                'Auction Management Panel</a>' % login_href,
            ),
            ('Username (Email)', '<strong>%s</strong>' % e(login or '—')),
            (
                'Temporary Password',
                '<strong style="font-family:Consolas,Menlo,monospace;">%s</strong>'
                % e(password or ''),
            ),
        )
        row_html = []
        for label, value in rows:
            row_html.append(
                '<tr>'
                '<td style="padding:7px 10px 7px 0;color:#4a5568;vertical-align:top;'
                'width:168px;">&bull;&nbsp;%s</td>'
                '<td style="padding:7px 0;color:#1a202c;vertical-align:top;">%s</td>'
                '</tr>' % (e(label), value)
            )

        return (
            '<div style="margin:0;padding:24px 12px;background:#f4f7fb;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'align="center" style="width:100%%;max-width:640px;background:#ffffff;'
            'border:1px solid #e2e8f0;border-radius:12px;">'
            '<tr><td style="padding:0;background:#1565c0;border-radius:12px 12px 0 0;'
            'line-height:0;font-size:0;">'
            '<img src="cid:ac-logo" width="640" height="74" alt="Auction Champ" '
            'style="display:block;border:0;width:100%%;max-width:640px;height:auto;"/>'
            '</td></tr>'
            '<tr><td style="height:4px;background:#f5a623;font-size:0;line-height:0;">&nbsp;</td></tr>'
            '<tr><td style="padding:28px 28px 8px;font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;line-height:1.55;color:#1a202c;">'
            '<h1 style="margin:0 0 18px;font-family:Georgia,Times New Roman,serif;'
            'font-size:22px;line-height:1.35;color:#0d1b2a;font-weight:normal;">'
            'Auction Champ&trade; | Your Complete Welcome &amp; Setup Guide</h1>'
            '<p style="margin:0 0 14px;">Hi %s,</p>'
            '<p style="margin:0 0 14px;">Welcome to Auction Champ!</p>'
            '<p style="margin:0 0 14px;">Thank you for choosing Auction Champ to power '
            'your tournament auctions.</p>'
            '%s'
            '<p style="margin:0 0 18px;">Your account is now active and ready to be '
            'configured. Below are your subscription details and login credentials '
            'to help you get started.</p>'
            '<h2 style="margin:0 0 8px;font-family:Georgia,Times New Roman,serif;'
            'font-size:18px;color:#0d1b2a;font-weight:normal;border-bottom:2px solid #f5a623;'
            'padding-bottom:6px;">Your Subscription Details</h2>'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'style="width:100%%;margin:0 0 16px;font-size:15px;">%s</table>'
            '<p style="margin:0 0 18px;padding:12px 14px;background:#fff8e8;'
            'border-left:3px solid #f5a623;">For security reasons, please log in using '
            'the credentials provided above and change your temporary password '
            'immediately after your first login.</p>'
            '<h2 style="margin:0 0 8px;font-family:Georgia,Times New Roman,serif;'
            'font-size:18px;color:#0d1b2a;font-weight:normal;">Get Started with Auction Champ</h2>'
            '<p style="margin:0 0 10px;">Follow our easy-to-use User Manual to configure '
            'your tournament, set auction rules, manage players, and conduct your auction.</p>'
            '<p style="margin:0 0 10px;">The manual includes step-by-step instructions and '
            'helpful solutions to common issues, ensuring a smooth auction experience.</p>'
            '<p style="margin:0 0 18px;">User Manual: '
            '<a href="%s" style="color:#1565c0;text-decoration:none;">%s</a></p>'
            '<h2 style="margin:0 0 8px;font-family:Georgia,Times New Roman,serif;'
            'font-size:18px;color:#0d1b2a;font-weight:normal;">We Are Here To HELP!</h2>'
            '<p style="margin:0 0 8px;">Need assistance? Our support team is always happy '
            'to help you.</p>'
            '<p style="margin:0 0 12px;">If you encounter any issues during setup or while '
            'conducting your auction, please feel free to reach out to us:</p>'
            '<p style="margin:0 0 8px;">'
            '<a href="%s" style="color:#1565c0;text-decoration:none;">'
            '&#9993; %s</a></p>'
            '<p style="margin:0 0 18px;">'
            '<a href="%s" style="text-decoration:none;">'
            '<img src="cid:ac-whatsapp" width="22" height="22" alt="WhatsApp" '
            'style="border:0;vertical-align:middle;width:22px;height:22px;"/>'
            '</a>'
            '&nbsp;<a href="%s" style="color:#128C7E;text-decoration:none;'
            'font-weight:bold;">WhatsApp</a>'
            '&nbsp;&nbsp;'
            '<a href="%s" style="text-decoration:none;">'
            '<img src="cid:ac-phone" width="22" height="22" alt="Phone" '
            'style="border:0;vertical-align:middle;width:22px;height:22px;"/>'
            '</a>'
            '&nbsp;<a href="%s" style="color:#1a202c;text-decoration:none;'
            'font-weight:bold;">%s</a>'
            '</p>'
            '<p style="margin:0 0 14px;">We wish you a successful tournament and an '
            'exciting auction experience with Auction Champ!</p>'
            '<p style="margin:0 0 18px;">Thank you for being part of the Auction Champ '
            'community.</p>'
            '<p style="margin:0;">Warm regards,<br/>'
            '<strong>Team Auction Champ</strong><br/>'
            '<a href="%s" style="color:#1565c0;text-decoration:none;">www.auctionchamp.live</a>'
            '</p>'
            '</td></tr>'
            '<tr><td style="padding:16px 28px 22px;font-family:Arial,Helvetica,sans-serif;'
            'font-size:12px;color:#718096;">This message includes your temporary password. '
            'Please keep it private.</td></tr>'
            '</table></div>'
        ) % (
            e(name or 'there'),
            payment_note,
            ''.join(row_html),
            manual_href,
            e(manual_url or ''),
            e(mailto, quote=True),
            e(SAAS_SUPPORT_EMAIL),
            e(wa_href, quote=True),
            e(wa_href, quote=True),
            e(tel_href, quote=True),
            e(tel_href, quote=True),
            e(SAAS_SUPPORT_PHONE_DISPLAY),
            e(SAAS_PUBLIC_SITE, quote=True),
        )

    @api.model
    def _saas_welcome_inline_images(self):
        """Logo and contact icons embedded in the welcome mail.

        The names start with ``cid:`` so the mail server sends them inline.
        The letter then shows them without fetching the public website.
        """
        root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', '..',
            'ac_saas_payment', 'static', 'src', 'img', 'email',
        ))
        specs = (
            ('cid:ac-logo.png', 'header_logo.png'),
            ('cid:ac-whatsapp.png', 'whatsapp.png'),
            ('cid:ac-phone.png', 'phone.png'),
        )
        found = []
        for name, filename in specs:
            path = os.path.join(root, filename)
            try:
                with open(path, 'rb') as handle:
                    payload = handle.read()
            except OSError:
                _logger.warning('Welcome email image missing: %s', path)
                continue
            if payload:
                found.append((name, payload, 'image/png'))
        return found

    def action_send_credentials_email(self, password=None, email_to=None, extra_attachments=None):
        """Email the welcome letter and login credentials.

        Called from website Get Started after payment, and from the manager
        resend button. Without an explicit ``password``, a new temporary
        password is generated. ``extra_attachments`` is a list of
        ``(filename, raw_bytes, mimetype)`` — the website signup passes the
        invoice PDF.
        """
        self.ensure_one()
        if 'mail.mail' not in self.env:
            _logger.warning(
                'mail module missing; cannot email credentials for SaaS account %s',
                self.id,
            )
            return False

        user = self.user_id.sudo().with_context(active_test=False)
        email = (email_to or user.email or user.login or '').strip()
        if not email:
            _logger.warning(
                'No email on SaaS account %s (%s); credentials not sent',
                self.id, self.name,
            )
            return False

        plain = password
        if not plain:
            plain = self._generate_temp_password()
            user.with_context(no_reset_password=True).write({'password': plain})

        attachments = []
        for item in (extra_attachments or []):
            if not item or len(item) < 2 or not item[1]:
                continue
            filename, payload = item[0], item[1]
            mimetype = item[2] if len(item) > 2 else 'application/octet-stream'
            attachments.append((filename, payload, mimetype))
        attachments.extend(self._saas_welcome_inline_images())
        invoice_attached = any(
            len(item) > 2 and item[2] == 'application/pdf' for item in attachments
        )

        public_base = self._saas_public_base_url()
        body = self._saas_welcome_email_html(
            name=user.name or self.name,
            plan=self.plan_id.name or '',
            account=self.name or '',
            valid_until=self._saas_format_date(self.date_end),
            login=user.login or email,
            password=plain,
            invoice_attached=invoice_attached,
            login_url='%s/web/login' % public_base,
            manual_url='%s/user-manual' % public_base,
        )
        try:
            mail_server = self._saas_mail_server()
            self._saas_ensure_mail_default_from()
            sender = self._saas_sender_address()
            try:
                email_from = formataddr(('Auction Champ', sender))
            except Exception:
                email_from = sender
            attachment_cmds = []
            Attachment = self.env['ir.attachment'].sudo()
            for filename, payload, mimetype in attachments:
                att = Attachment.create({
                    'name': filename,
                    'datas': base64.b64encode(payload),
                    'type': 'binary',
                    'mimetype': mimetype,
                    'res_model': 'ac.saas.account',
                    'res_id': self.id,
                })
                attachment_cmds.append((4, att.id))
            mail = self.env['mail.mail'].sudo().create({
                'subject': SAAS_WELCOME_SUBJECT,
                'body_html': body,
                'email_from': email_from,
                'reply_to': sender,
                'email_to': email,
                'message_id': self._saas_message_id(),
                'mail_server_id': mail_server.id if mail_server else False,
                'auto_delete': False,
                'attachment_ids': attachment_cmds,
            })
            mail.sudo().send()
            if mail.exists() and mail.state == 'exception':
                _logger.error(
                    'SaaS welcome mail exception for account %s to %s: %s',
                    self.id, email, mail.failure_reason or mail.state,
                )
                return False
            _logger.info(
                'SaaS welcome mailed account=%s to=%s invoice_attached=%s state=%s',
                self.id,
                email,
                invoice_attached,
                mail.state if mail.exists() else 'gone',
            )
        except Exception:
            _logger.exception(
                'Failed to email SaaS welcome for account %s to %s',
                self.id, email,
            )
            return False
        return True

    def action_email_login_credentials(self):
        """Manager button: reset temp password and email login details."""
        self.ensure_one()
        if not self.user_id:
            raise UserError(_('This account has no login user.'))
        ok = self.action_send_credentials_email()
        if not ok:
            raise UserError(_(
                'Could not deliver the credentials email. '
                'Open Settings → Technical → Email → Emails, open the '
                '"Delivery Failed" row, and read Failure Reason. '
                'From must be the same mailbox as the outgoing SMTP user '
                '(Gmail/Office 365 reject a different From).'
            ))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Credentials sent'),
                'message': _(
                    'A temporary password was generated and emailed to %s.'
                ) % (self.user_id.email or self.user_id.login),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        accounts._assign_account_user_group()
        accounts._sync_user_groups()
        accounts._sync_user_tournament_links()
        return accounts

    def write(self, vals):
        vals = dict(vals)
        if vals.get('plan_id'):
            plan = self.env['ac.saas.plan'].browse(vals['plan_id'])
            if plan and not plan.allow_parallel_sessions:
                vals['disable_parallel_sessions'] = False
        res = super().write(vals)
        if any(k in vals for k in ('plan_id', 'state', 'active', 'user_id')):
            self._assign_account_user_group()
            self._sync_user_groups()
            self._sync_user_tournament_links()
        if any(k in vals for k in ('state', 'active', 'user_id')):
            self._apply_login_access()
        return res

    def _sync_user_tournament_links(self):
        """Keep res.users.tournament_ids in sync for legacy record rules."""
        Tournament = self.env['auction.tournament'].sudo()
        for acc in self:
            user = acc.user_id
            if not user:
                continue
            user = user.sudo()
            # Claim tournaments already assigned to this user but missing SaaS link
            orphans = Tournament.search([
                ('saas_account_id', '=', False),
                '|',
                ('id', 'in', user.tournament_ids.ids or [0]),
                ('organizer_uids', 'in', [user.id]),
            ])
            if orphans:
                orphans.write({'saas_account_id': acc.id})

            tournaments = acc.tournament_ids
            for tournament in tournaments:
                if tournament not in user.tournament_ids:
                    user.write({'tournament_ids': [(4, tournament.id)]})
            if tournaments and not user.tournament_id:
                user.write({'tournament_id': tournaments[:1].id})

    @api.model
    def _sync_all_user_tournament_links(self):
        """Called on module upgrade to repair organiser tournament links."""
        self.search([])._sync_user_tournament_links()
        return True

    def _assign_account_user_group(self):
        try:
            group = self.env.ref('ac_saas_manager.group_saas_account_user')
        except ValueError:
            return
        for acc in self:
            if not acc.user_id:
                continue
            user = acc.user_id.sudo().with_context(active_test=False)
            if acc.active and acc.state in ('active', 'expired'):
                user.write({'groups_id': [(4, group.id)]})
            else:
                user.write({'groups_id': [(3, group.id)]})
    def _module_installed(self, technical_name):
        return bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', technical_name),
            ('state', '=', 'installed'),
        ]))

    def _sync_user_groups(self):
        """Map plan feature flags → organiser app groups (plan is the only setting).

        Admins toggle features on ``ac.saas.plan``; this method grants/revokes the
        matching ``res.groups`` so menus appear without any manual group setup.
        """
        for acc in self:
            user = acc.user_id
            if not user:
                continue
            plan = acc.plan_id
            active = acc.active and acc.state == 'active' and plan
            user = user.sudo()

            def _set_group(xmlid, enabled):
                try:
                    group = self.env.ref(xmlid)
                except ValueError:
                    return
                if not group:
                    return
                if enabled:
                    user.write({'groups_id': [(4, group.id)]})
                else:
                    user.write({'groups_id': [(3, group.id)]})

            if self._module_installed('auction_module'):
                # Player Detail Dashboard — always for active/expired SaaS organisers
                can_use = bool(
                    acc.active
                    and acc.state in ('active', 'expired')
                    and plan
                )
                _set_group(
                    'auction_module.group_auction_player_dashboard',
                    can_use,
                )
                # Pool creator
                _set_group(
                    'auction_module.group_auction_pool_generator',
                    bool(active and plan.allow_pool_creator),
                )
                # Player card print — any plan that lists allowed card templates
                has_cards = bool(
                    active and plan.get_allowed_templates()
                )
                _set_group(
                    'auction_module.group_auction_player_card_print',
                    has_cards,
                )

            # Auctioneer Console — driven only by plan.allow_auctioneer_console
            if self._module_installed('auction_auctioneer'):
                _set_group(
                    'auction_auctioneer.group_auctioneer',
                    bool(active and plan.allow_auctioneer_console),
                )

            # Owner group — organisers are not auto-added; team owners are separate users.
            if self._module_installed('auction_owner'):
                try:
                    self.env.ref('auction_owner.group_auction_owner')
                except ValueError:
                    pass

    @api.model
    def _sync_all_user_groups(self):
        """Re-apply plan → group mapping for every SaaS account (upgrade repair)."""
        self.search([])._sync_user_groups()
        return True
