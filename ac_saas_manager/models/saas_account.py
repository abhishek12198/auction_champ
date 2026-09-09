# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — One account = one login
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


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

    # Mirrored plan limits (for UI)
    max_tournaments = fields.Integer(related='plan_id.max_tournaments', readonly=True)
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
                'Please request reactivation to continue.'
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
                    'Use "Request reactivation" to ask support to restore access.'
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

    def action_request_reactivation(self):
        """Customer action: request renewal during the 10-day window or after expiry."""
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

        today = fields.Date.context_today(self)
        if self.date_end:
            days_left = (self.date_end - today).days
            if self._is_frozen() or days_left < 0:
                note = _(
                    'Account expired on %(date)s — please renew / reactivate.'
                ) % {'date': self.date_end}
            else:
                note = _(
                    'Account is expiring on %(date)s (%(days)s day(s) left) — '
                    'please renew / reactivate.'
                ) % {'date': self.date_end, 'days': days_left}
        else:
            note = _('Please renew / reactivate this account.')

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
        current = self.env['auction.tournament'].sudo().search_count([
            ('saas_account_id', '=', self.id),
        ])
        if current >= plan.max_tournaments:
            raise ValidationError(_(
                'Your %(plan)s plan allows up to %(max)s tournament(s). '
                'You already have %(cur)s. Upgrade your plan or contact support.'
            ) % {
                'plan': plan.name,
                'max': plan.max_tournaments,
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
