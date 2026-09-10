# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — link login user ↔ account + tournament switcher
#
##############################################################################
import logging

from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request

from .res_users_session import AC_WORKING_TOURNAMENT_SESSION_KEY

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    saas_account_id = fields.Many2one(
        'ac.saas.account',
        string='SaaS Account',
        compute='_compute_saas_account_id',
        search='_search_saas_account_id',
    )

    def _compute_saas_account_id(self):
        Account = self.env['ac.saas.account'].sudo()
        for user in self:
            acc = Account.search([('user_id', '=', user.id)], limit=1)
            user.saas_account_id = acc

    def _search_saas_account_id(self, operator, value):
        accounts = self.env['ac.saas.account'].sudo().search([
            ('id', operator, value),
        ])
        return [('id', 'in', accounts.mapped('user_id').ids)]

    def _saas_assert_login_allowed(self):
        """Block authentication when the linked SaaS account is not active."""
        self.ensure_one()
        Account = self.env['ac.saas.account'].sudo().with_context(active_test=False)
        acc = Account.search([('user_id', '=', self.id)], limit=1)
        if not acc:
            return
        if acc.state in ('active', 'expired') and acc.active:
            return
        state_label = dict(acc._fields['state'].selection).get(acc.state, acc.state)
        raise AccessDenied(_(
            'Your AuctionChamp account "%(name)s" is %(state)s. '
            'Please contact support.'
        ) % {'name': acc.name, 'state': state_label})

    def _check_credentials(self, password, env):
        # Runs on login (and password checks). Refuse suspended / inactive accounts.
        self._saas_assert_login_allowed()
        return super()._check_credentials(password, env)

    @classmethod
    def _login(cls, db, login, password, user_agent_env):
        # Surface a clear suspended-account message even when the login user
        # was archived by action_suspend (default search skips inactive users).
        if login:
            try:
                with cls.pool.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    Users = env['res.users'].with_context(active_test=False)
                    user = Users.search(
                        Users._get_login_domain(login),
                        order=Users._get_login_order(),
                        limit=1,
                    )
                    if user:
                        user._saas_assert_login_allowed()
            except AccessDenied:
                ip = request.httprequest.environ['REMOTE_ADDR'] if request else 'n/a'
                _logger.info(
                    "Login blocked (SaaS account not active) for db:%s login:%s from %s",
                    db, login, ip,
                )
                raise
        return super(ResUsers, cls)._login(db, login, password, user_agent_env)

    def get_saas_account(self):
        """Return ac.saas.account for this user, or empty recordset."""
        self.ensure_one()
        return self.env['ac.saas.account']._get_account_for_user(self)

    def _saas_switchable_tournaments(self):
        """Tournaments this login may enable (account-owned, else auction rules).

        SaaS organisers: every tournament on their ``ac.saas.account``.
        Everyone else (incl. admins): same as ``_auction_switchable_tournaments``
        so admins see all active tournaments, not only ``tournament_ids``.
        """
        self.ensure_one()
        Tournament = self.env['auction.tournament'].sudo()
        account = self.get_saas_account()
        if account:
            return Tournament.browse(account.sudo().tournament_ids.ids)
        return self._auction_switchable_tournaments()

    @api.model
    def get_systray_tournaments(self):
        """Payload for the navbar tournament switcher badge.

        The dropdown lists at most 10 tournaments (working tournament first).
        Use ``search_systray_tournaments`` for the full searchable picker.
        """
        user = self.env.user
        tournaments = user._saas_switchable_tournaments()
        working = user.get_working_tournament()
        active_id = working.id if working else False
        parallel = user._saas_parallel_sessions_enabled()
        items = user._auction_systray_items(tournaments, active_id)
        # Keep the working tournament in the short list even if sorted later
        if active_id:
            active_items = [i for i in items if i.get('id') == active_id]
            other_items = [i for i in items if i.get('id') != active_id]
            items = active_items + other_items
        total = len(items)
        limit = 10
        preview = items[:limit]
        current = next((i for i in items if i['active']), items[0] if items else None)
        account = user.get_saas_account()
        return {
            'tournaments': preview,
            'tournament_total': total,
            'has_more_tournaments': total > limit,
            'current': current,
            'can_switch': total > 1,
            'parallel_sessions': parallel,
            'working_scope_hint': user._saas_working_scope_hint(parallel),
            'plan': user._get_systray_plan_info(),
            'expiry_warning': user._get_saas_expiry_warning(),
            'account_frozen': user._saas_account_is_frozen(),
            'can_request_renewal': user._saas_can_request_renewal(),
            'saas_account_id': account.id if account else False,
        }

    @api.model
    def search_systray_tournaments(self, query='', limit=80, offset=0):
        """Searchable list of tournaments this login may switch to."""
        user = self.env.user
        tournaments = user._saas_switchable_tournaments()
        working = user.get_working_tournament()
        active_id = working.id if working else False
        q = (query or '').strip().lower()
        if q:
            tournaments = tournaments.filtered(
                lambda t: q in (t.name or '').lower()
            )
        # Stable order: active record flag from DB, then name
        tournaments = tournaments.sorted(
            key=lambda t: (not t.active, (t.name or '').lower(), t.id)
        )
        total = len(tournaments)
        try:
            limit = max(1, min(int(limit or 80), 200))
        except (TypeError, ValueError):
            limit = 80
        try:
            offset = max(0, int(offset or 0))
        except (TypeError, ValueError):
            offset = 0
        page = tournaments[offset:offset + limit]
        items = user._auction_systray_items(page, active_id)
        return {
            'tournaments': items,
            'total': total,
            'offset': offset,
            'limit': limit,
            'query': query or '',
        }

    def _saas_account_is_frozen(self):
        self.ensure_one()
        account = self.get_saas_account()
        if not account:
            return False
        return account._is_frozen()

    def _saas_can_request_renewal(self):
        self.ensure_one()
        account = self.get_saas_account()
        return bool(account and account._can_request_renewal())

    def _get_saas_expiry_warning(self):
        """Warn when the SaaS account end date is within 10 days (or already past)."""
        self.ensure_one()
        account = self.get_saas_account()
        if not account or not account.date_end:
            return False
        if account.state not in ('active', 'expired'):
            return False
        today = fields.Date.context_today(self)
        days_left = (account.date_end - today).days
        frozen = account._is_frozen()
        if days_left > 10 and not frozen:
            return False
        if frozen or days_left < 0:
            message = _(
                'Your account has expired. It is frozen — you cannot change data. '
                'Renew your plan to continue using it further.'
            )
            days_left = min(days_left, -1)
        elif days_left == 0:
            message = _(
                'Your account is expiring today. Renew your plan '
                'to continue using it further.'
            )
        elif days_left == 1:
            message = _(
                'Your account is expiring in 1 day. Renew your plan '
                'to continue using it further.'
            )
        else:
            message = _(
                'Your account is expiring in %(days)s days. Renew your plan '
                'to continue using it further.'
            ) % {'days': days_left}
        return {
            'days_left': days_left,
            'date_end': fields.Date.to_string(account.date_end),
            'urgent': frozen or days_left <= 3,
            'frozen': frozen,
            'message': message,
        }

    def _saas_working_scope_hint(self, parallel=None):
        self.ensure_one()
        if parallel is None:
            parallel = self._saas_parallel_sessions_enabled()
        if parallel:
            return _(
                'Parallel mode: this browser only. Other devices can run another tournament.'
            )
        return _(
            'Shared mode: switching here updates the working tournament on all your devices.'
        )

    def _get_systray_plan_info(self):
        """Compact plan summary for the navbar (SaaS account users only)."""
        self.ensure_one()
        account = self.get_saas_account()
        if not account or not account.plan_id:
            return False
        plan = account.plan_id
        themes = plan.get_allowed_templates() or []
        theme_labels = {
            'lemon': _('Lemon'),
            'vanilla': _('Vanilla'),
            'butterscotch': _('Butterscotch'),
            'strawberry': _('Strawberry'),
            'cherry': _('Cherry'),
            'pistah': _('Pistah'),
            'blackberry': _('Blackberry'),
        }
        theme_names = [theme_labels.get(k, k.title()) for k in themes]
        higher = self.env['ac.saas.plan'].sudo().search_count([
            ('active', '=', True),
            ('sequence', '>', plan.sequence),
        ])
        parallel_line = _('Parallel tournaments (multi-device): %s') % (
            _('Yes') if plan.allow_parallel_sessions else _('No')
        )
        if plan.allow_parallel_sessions and account.disable_parallel_sessions:
            parallel_line += ' ' + _('(disabled for this account)')
        expiry_display = self._format_saas_expiry_date(account.date_end)
        used = account._tournament_count_for_quota()
        limit = account._effective_tournament_limit()
        lines = [
            _('Tournaments: %(used)s of %(limit)s') % {
                'used': used,
                'limit': limit,
            },
            _('Teams / tournament: up to %s') % plan.max_teams_per_tournament,
            _('Players / tournament: up to %s') % plan.max_players_per_tournament,
            _('Random mode: %s') % (_('Yes') if plan.allow_random_mode else _('No')),
            _('Auctioneer console: %s') % (
                _('Yes') if plan.allow_auctioneer_console else _('No')
            ),
            _('Mystery players: %s') % (
                _('Yes') if plan.allow_mystery_players else _('No')
            ),
            parallel_line,
            _('Themes: %s') % (', '.join(theme_names) if theme_names else '—'),
        ]
        return {
            'name': plan.name,
            'code': plan.code,
            'account_id': account.id,
            'account_name': account.name or '',
            'expiry_display': expiry_display or '',
            'can_upgrade': bool(higher),
            'lines': lines,
        }

    @api.model
    def _format_saas_expiry_date(self, date_val):
        """Format date as '10th May 2026'."""
        if not date_val:
            return False
        day = date_val.day
        if 11 <= day <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return '%d%s %s %d' % (day, suffix, date_val.strftime('%B'), date_val.year)

    @api.model
    def action_saas_open_upgrade_wizard(self):
        """Open upgrade-request wizard from the navbar plan chip."""
        account = self.env['ac.saas.account']._get_account_for_user()
        if not account:
            raise UserError(_(
                'No SaaS account is linked to your login. Please contact support.'
            ))
        tournament = self.env.user.get_working_tournament()
        tournament_id = (
            tournament.id
            if tournament and tournament.saas_account_id == account
            else False
        )
        return account.action_open_upgrade_wizard(
            trigger_feature='other',
            tournament_id=tournament_id,
        )

    def set_active_tournament(self, tournament_id):
        """Set working tournament for menus and creates (session or global)."""
        self.ensure_one()
        if self.env.user != self and not self.env.su:
            raise AccessError(_('You can only switch your own active tournament.'))
        tournament_id = int(tournament_id or 0)
        if not tournament_id:
            raise UserError(_('Select a tournament to enable.'))

        allowed = self._saas_switchable_tournaments()
        tournament = allowed.filtered(lambda t: t.id == tournament_id)
        if not tournament:
            raise AccessError(_(
                'You cannot enable that tournament — it is not linked to your account.'
            ))

        parallel = self._saas_parallel_sessions_enabled()
        if parallel:
            self._saas_seed_session_tournament(tournament.id)
        else:
            session = self._saas_http_session()
            if session is not None and AC_WORKING_TOURNAMENT_SESSION_KEY in session:
                del session[AC_WORKING_TOURNAMENT_SESSION_KEY]
            vals = {}
            if self.tournament_id.id != tournament.id:
                vals['tournament_id'] = tournament.id
            if tournament.id not in self.tournament_ids.ids:
                vals['tournament_ids'] = [(4, tournament.id)]
            if vals:
                self.sudo().with_context(
                    skip_tournament_sync=True,
                    mail_notrack=True,
                    tracking_disable=True,
                ).write(vals)
        return self.get_systray_tournaments()
