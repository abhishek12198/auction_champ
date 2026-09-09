# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — tournament quotas & feature gates
#  (inherits auction.tournament — does not edit auction_module files)
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    saas_account_id = fields.Many2one(
        'ac.saas.account',
        string='SaaS Account',
        index=True,
        ondelete='restrict',
        help='Owning SaaS account (one login). Set automatically for account users.',
    )
    # Stored for reliable ir.rule domains (related path can fail on create)
    saas_user_id = fields.Many2one(
        'res.users',
        string='SaaS User',
        related='saas_account_id.user_id',
        store=True,
        index=True,
        readonly=True,
    )
    saas_allow_random_mode = fields.Boolean(
        string='Plan Allows Random',
        compute='_compute_saas_mode_hints',
    )
    saas_random_upgrade_hint = fields.Char(
        string='Random Upgrade Hint',
        compute='_compute_saas_mode_hints',
    )
    saas_theme_restricted = fields.Boolean(
        string='Theme Restricted by Plan',
        compute='_compute_saas_mode_hints',
    )
    saas_theme_upgrade_hint = fields.Char(
        string='Theme Upgrade Hint',
        compute='_compute_saas_mode_hints',
    )
    saas_allowed_theme_keys = fields.Char(
        string='Allowed Theme Keys',
        compute='_compute_saas_mode_hints',
        help='Comma-separated player card themes allowed by the SaaS plan. '
             'Empty means all themes are available.',
    )
    saas_allowed_algorithm_keys = fields.Char(
        string='Allowed Call-Up Modes',
        compute='_compute_saas_mode_hints',
        help='Comma-separated call-up mode keys (linear, random). '
             'Empty means both modes are available.',
    )
    saas_can_request_upgrade = fields.Boolean(
        string='Can Request Upgrade',
        compute='_compute_saas_mode_hints',
    )
    saas_max_players = fields.Integer(
        string='Plan Max Players',
        compute='_compute_saas_mode_hints',
    )
    saas_max_registrations_hint = fields.Char(
        string='Max Registrations Hint',
        compute='_compute_saas_mode_hints',
    )
    is_saas_active = fields.Boolean(
        string='Active in Navbar',
        compute='_compute_is_saas_active',
        help='This tournament is currently selected in the top navbar switcher. '
             'Menus, player lists, showcase and projector shortcuts use this tournament.',
    )
    saas_active_label = fields.Char(
        string='Working tournament',
        compute='_compute_is_saas_active',
    )
    saas_active_help = fields.Char(
        string='Navbar help',
        compute='_compute_is_saas_active',
    )

    def _compute_is_saas_active(self):
        active_id = self.env.user.get_working_tournament_id()
        parallel = self.env.user._saas_parallel_sessions_enabled()
        for tournament in self:
            is_active = bool(active_id and tournament.id == active_id)
            tournament.is_saas_active = is_active
            tournament.saas_active_label = _('WORKING NOW') if is_active else _('NOT WORKING')
            if is_active:
                if parallel:
                    tournament.saas_active_help = _(
                        'Working tournament in this browser — selected in the top navbar. '
                        'Other devices can use another tournament if your plan allows parallel mode.'
                    )
                else:
                    tournament.saas_active_help = _(
                        'This is your working tournament — selected in the top navbar. '
                        'Players, teams and showcase menus use this one on all your devices. '
                        'To switch, use the navbar badge or open another tournament and click “Use this tournament”.'
                    )
            elif parallel:
                tournament.saas_active_help = _(
                    'Not the working tournament in this browser. '
                    'Menus and lists here follow the one selected in the top navbar on this device.'
                )
            else:
                tournament.saas_active_help = _(
                    'This tournament is not your working tournament. '
                    'Menus, players and showcase still point to the one selected in the top navbar. '
                    'Click “Use this tournament” (or switch from the navbar) to work on this one.'
                )

    def action_saas_set_active(self):
        """Select this tournament in the navbar switcher (reload to refresh UI)."""
        self.ensure_one()
        self.env.user.set_active_tournament(self.id)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.depends('saas_account_id', 'saas_account_id.plan_id',
                 'saas_account_id.plan_id.allow_random_mode',
                 'saas_account_id.plan_id.allowed_player_templates',
                 'saas_account_id.plan_id.sequence',
                 'saas_account_id.plan_id.max_players_per_tournament')
    def _compute_saas_mode_hints(self):
        Account = self.env['ac.saas.account']
        Plan = self.env['ac.saas.plan']
        for tournament in self:
            account = tournament.saas_account_id or Account._get_account_for_user()
            plan = account.plan_id if account else Plan.browse()
            allow_random = bool(plan.allow_random_mode) if plan else True
            tournament.saas_allow_random_mode = allow_random
            if plan and not allow_random:
                upgrade = Plan.get_min_plan_for_random()
                tournament.saas_random_upgrade_hint = _(
                    '%(plan)s plan · Roll Call only · Lucky Dip needs %(upgrade)s+'
                ) % {
                    'plan': plan.name,
                    'upgrade': upgrade.name if upgrade else 'Classic',
                }
            else:
                tournament.saas_random_upgrade_hint = False

            # Theme restriction: plan lists a subset of themes
            all_keys = {
                'lemon', 'vanilla', 'butterscotch', 'strawberry', 'cherry', 'pistah',
                'blackberry',
            }
            allowed = plan.get_allowed_templates() if plan else []
            restricted = bool(plan and allowed and set(allowed) < all_keys)
            tournament.saas_theme_restricted = restricted
            tournament.saas_theme_upgrade_hint = (
                plan.get_theme_upgrade_hint() if restricted else False
            )
            # Empty string → widget shows every theme (admins / no plan)
            tournament.saas_allowed_theme_keys = (
                ','.join(allowed) if (plan and allowed) else ''
            )
            # Call-up mode: Lucky Dip first when allowed; Roll Call always
            if plan:
                algo_keys = []
                if plan.allow_random_mode:
                    algo_keys.append('random')
                algo_keys.append('linear')
                tournament.saas_allowed_algorithm_keys = ','.join(algo_keys)
            else:
                tournament.saas_allowed_algorithm_keys = ''
            if account and plan:
                higher = Plan.search_count([
                    ('active', '=', True),
                    ('sequence', '>', plan.sequence),
                ])
                tournament.saas_can_request_upgrade = bool(higher)
                tournament.saas_max_players = plan.max_players_per_tournament
                tournament.saas_max_registrations_hint = _(
                    '%(plan)s plan · max %(max)s registrations (unlimited not available)'
                ) % {
                    'plan': plan.name,
                    'max': plan.max_players_per_tournament,
                }
            else:
                tournament.saas_can_request_upgrade = False
                tournament.saas_max_players = 0
                tournament.saas_max_registrations_hint = False

    def _saas_plan_for_tournament(self):
        """Plan linked to this tournament (or current SaaS user), else empty."""
        self.ensure_one()
        account = self.saas_account_id or self.env['ac.saas.account']._get_account_for_user()
        return account.plan_id if account else self.env['ac.saas.plan'].browse()

    @api.model
    def default_get(self, fields_list):
        """Prefill plan-safe defaults for SaaS users (registrations + theme)."""
        defaults = super().default_get(fields_list)
        account = self.env['ac.saas.account']._get_account_for_user()
        if account and account.plan_id:
            plan = account.plan_id
            plan_max = int(plan.max_players_per_tournament or 0)
            if plan_max > 0 and (
                'max_registrations' in fields_list
                or not fields_list
            ):
                current = int(defaults.get('max_registrations') or 0)
                if current <= 0 or current > plan_max:
                    defaults['max_registrations'] = plan_max
            if 'saas_account_id' in fields_list or not fields_list:
                defaults.setdefault('saas_account_id', account.id)
            # Default to the first theme included in the active plan (not core
            # default 'lemon', which may be locked and triggers a warning).
            if 'player_display_template' in fields_list or not fields_list:
                allowed = plan.get_allowed_templates()
                if allowed:
                    chosen = defaults.get('player_display_template')
                    if not chosen or chosen not in allowed:
                        defaults['player_display_template'] = allowed[0]
            if 'player_appearance_algorithm' in fields_list or not fields_list:
                if plan.allow_random_mode:
                    defaults['player_appearance_algorithm'] = 'random'
                else:
                    defaults['player_appearance_algorithm'] = 'linear'
        return defaults

    def _saas_effective_max_registrations(self):
        """Registration ceiling used by /player/register (plan-capped for SaaS)."""
        self.ensure_one()
        plan = self._saas_plan_for_tournament()
        max_reg = int(self.max_registrations or 0)
        if not plan:
            return max_reg
        plan_max = int(plan.max_players_per_tournament or 0)
        if plan_max <= 0:
            return max_reg
        # SaaS: never unlimited; never above plan
        if max_reg <= 0:
            return plan_max
        return min(max_reg, plan_max)

    def _saas_clamp_max_registrations(self, value, plan=None):
        """Return a plan-safe max_registrations value (0/over → plan max)."""
        self.ensure_one()
        plan = plan or self._saas_plan_for_tournament()
        if not plan:
            return int(value or 0)
        plan_max = int(plan.max_players_per_tournament or 0)
        if plan_max <= 0:
            return int(value or 0)
        req = int(value or 0)
        if req <= 0 or req > plan_max:
            return plan_max
        return req

    @api.onchange('max_registrations')
    def _onchange_saas_max_registrations(self):
        plan = self._saas_plan_for_tournament()
        if not plan:
            return
        plan_max = int(plan.max_players_per_tournament or 0)
        if plan_max <= 0:
            return
        req = int(self.max_registrations or 0)
        if req <= 0:
            # 0 means unlimited in core — silently use plan default (no popup).
            # New-form onchange used to fire this as a scary warning and look
            # like a tournament-create block.
            self.max_registrations = plan_max
            return
        if req > plan_max:
            self.max_registrations = plan_max
            return {
                'warning': {
                    'title': _('Plan registration limit'),
                    'message': _(
                        'Your %(plan)s plan allows up to %(max)s player registrations '
                        'per tournament.'
                    ) % {
                        'plan': plan.name,
                        'max': plan_max,
                    },
                }
            }

    def action_saas_request_upgrade(self):
        """Open the upgrade-request wizard (optional trigger from context)."""
        self.ensure_one()
        account = self.saas_account_id or self.env['ac.saas.account']._get_account_for_user()
        if not account:
            raise ValidationError(_(
                'No SaaS account is linked to your login. Please contact support.'
            ))
        trigger = self.env.context.get('saas_upgrade_trigger', 'other')
        return account.action_open_upgrade_wizard(
            trigger_feature=trigger,
            tournament_id=self.id,
        )

    def _saas_current_plan(self):
        """Plan for this tournament / current SaaS user, or empty."""
        self.ensure_one()
        account = self.saas_account_id or self.env['ac.saas.account']._get_account_for_user()
        return account.plan_id if account else self.env['ac.saas.plan'].browse()

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        account = self.env['ac.saas.account']._get_account_for_user()
        if not account or not account.plan_id:
            return res
        plan = account.plan_id

        algo_key = 'player_appearance_algorithm'
        if algo_key in res:
            res[algo_key]['selection'] = [
                ('random', plan.get_random_selection_label()),
                ('linear', _('Roll Call')),
            ]
            res[algo_key]['string'] = _('Player Call-Up Mode')

        theme_key = 'player_display_template'
        if theme_key in res and res[theme_key].get('selection'):
            res[theme_key]['selection'] = [
                (key, plan.get_template_selection_label(key, label))
                for key, label in res[theme_key]['selection']
            ]
        return res

    @api.onchange('player_appearance_algorithm')
    def _onchange_saas_player_appearance_algorithm(self):
        plan = self._saas_current_plan()
        if not plan or plan.allow_random_mode:
            return
        if self.player_appearance_algorithm == 'random':
            self.player_appearance_algorithm = 'linear'
            upgrade = self.env['ac.saas.plan'].get_min_plan_for_random()
            return {
                'warning': {
                    'title': _('Lucky Dip not available'),
                    'message': _(
                        'Your %(plan)s plan only includes Roll Call '
                        '(list order or dice by squad number).\n'
                        'Upgrade to %(upgrade)s to enable Lucky Dip.'
                    ) % {
                        'plan': plan.name,
                        'upgrade': upgrade.name if upgrade else 'Classic',
                    },
                }
            }

    @api.onchange('player_display_template', 'saas_account_id')
    def _onchange_saas_player_display_template(self):
        """Keep theme on an allowed plan value — silent when fixing plan defaults."""
        plan = self._saas_current_plan()
        if not plan:
            return
        allowed = plan.get_allowed_templates()
        if not allowed:
            return
        chosen = self.player_display_template
        if chosen and chosen in allowed:
            return
        fallback = allowed[0]
        # Invalid / empty / locked theme → first theme on the active plan.
        # No warning popup: new forms used to default to Lemon and scare users
        # whose plan does not include it.
        self.player_display_template = fallback
        return

    @api.model
    def _saas_resolve_account(self, vals=None):
        vals = vals or {}
        if vals.get('saas_account_id'):
            return self.env['ac.saas.account'].browse(vals['saas_account_id'])
        return self.env['ac.saas.account']._get_account_for_user()

    @api.model
    def _saas_prepare_for_account(self, account, tournament_id=None):
        """Return a tournament owned by *account*, linking legacy user fields.

        Prefer an explicit tournament_id, then the user's active tournament
        (navbar switcher), then any account tournament. Never force every
        create onto tournament_ids[:1] — that incorrectly applies per-tournament
        caps (teams/players) across the whole account.
        """
        from odoo.exceptions import AccessError, UserError

        account.ensure_one()
        Tournament = self.sudo()
        account_tournaments = account.sudo().tournament_ids
        account_ids = set(account_tournaments.ids)

        tournament = Tournament.browse()
        if tournament_id:
            try:
                tid = int(tournament_id)
            except (TypeError, ValueError):
                tid = False
            if tid:
                tournament = Tournament.browse(tid)

        if not tournament:
            # Active tournament from navbar / session (res.users helper)
            active = self.env.user.sudo().get_working_tournament()
            if active and active.id in account_ids:
                tournament = Tournament.browse(active.id)

        if not tournament and account_tournaments:
            tournament = account_tournaments[:1]

        if not tournament:
            raise UserError(_(
                'Create a tournament first, then add teams and players.'
            ))

        if tournament.saas_account_id and tournament.saas_account_id != account:
            raise AccessError(_(
                'You cannot use tournament "%(name)s" — it belongs to another account.'
            ) % {'name': tournament.name})

        if not tournament.saas_account_id:
            tournament.write({'saas_account_id': account.id})

        user = account.user_id.sudo()
        writes = {'tournament_ids': [(4, tournament.id)]}
        # Keep active tournament in sync when creating into a specific tournament
        if not user.tournament_id or user.tournament_id.id not in account_ids:
            writes['tournament_id'] = tournament.id
        user.write(writes)
        if hasattr(tournament, 'organizer_uids') and account.user_id not in tournament.organizer_uids:
            tournament.write({
                'organizer_uids': [(4, account.user_id.id)],
                'organizer_uid': tournament.organizer_uid.id or account.user_id.id,
            })
        return tournament

    @api.model_create_multi
    def create(self, vals_list):
        Account = self.env['ac.saas.account']
        for vals in vals_list:
            account = self._saas_resolve_account(vals)
            if account:
                account.assert_not_frozen(operation='create tournaments')
                account.assert_can_create_tournament()
                plan = account.get_plan()
                vals['saas_account_id'] = account.id
                # Cap registrations to plan max if missing / too high
                max_p = plan.max_players_per_tournament
                if not vals.get('max_registrations') or vals.get('max_registrations', 0) <= 0:
                    vals['max_registrations'] = max_p
                else:
                    vals['max_registrations'] = min(int(vals['max_registrations']), max_p)
                # Lucky Dip is the default; Roll Call when the plan has no random.
                algo = vals.get('player_appearance_algorithm', 'random')
                if not plan.allow_random_mode:
                    vals['player_appearance_algorithm'] = 'linear'
                    algo = 'linear'
                plan.assert_random_mode_allowed(algo)
                # Theme whitelist — always prefer first allowed when missing/locked
                allowed = plan.get_allowed_templates()
                tpl = vals.get('player_display_template')
                if allowed and (not tpl or tpl not in allowed):
                    vals['player_display_template'] = allowed[0]
                elif tpl:
                    plan.assert_template_allowed(tpl)
        tournaments = super().create(vals_list)
        # Bind organiser user to their new tournament for existing record rules
        for tournament in tournaments:
            account = tournament.saas_account_id
            if account and account.user_id:
                user = account.user_id.sudo()
                # Always link — required by auction_module team/player rules
                user.write({
                    'tournament_ids': [(4, tournament.id)],
                    'tournament_id': user.tournament_id.id or tournament.id,
                })
                # Ensure user is on organizer M2M
                if hasattr(tournament, 'organizer_uids') and account.user_id not in tournament.organizer_uids:
                    tournament.sudo().write({
                        'organizer_uids': [(4, account.user_id.id)],
                        'organizer_uid': (
                            tournament.organizer_uid.id
                            if tournament.organizer_uid else account.user_id.id
                        ),
                    })
        return tournaments

    def write(self, vals):
        vals = dict(vals)
        account = self.env['ac.saas.account']._get_account_for_user()

        gated = {
            'player_appearance_algorithm',
            'player_display_template',
            'max_registrations',
        }
        if gated.intersection(vals):
            for tournament in self:
                owner = tournament.saas_account_id or account
                if not owner:
                    continue
                plan = owner.get_plan()
                if 'player_appearance_algorithm' in vals:
                    plan.assert_random_mode_allowed(vals['player_appearance_algorithm'])
                if 'player_display_template' in vals:
                    tpl = vals.get('player_display_template')
                    allowed = plan.get_allowed_templates()
                    if allowed and (not tpl or tpl not in allowed):
                        vals['player_display_template'] = allowed[0]
                    elif tpl:
                        plan.assert_template_allowed(tpl)

        # Cap max_registrations to the tournament's plan (never unlimited on SaaS)
        if 'max_registrations' in vals:
            req = vals.get('max_registrations')
            clamped_by_id = {}
            for tournament in self:
                owner = tournament.saas_account_id or account
                if not owner or not owner.plan_id:
                    continue
                clamped_by_id[tournament.id] = tournament._saas_clamp_max_registrations(
                    req, owner.plan_id
                )
            if clamped_by_id:
                if len(self) == 1:
                    vals['max_registrations'] = next(iter(clamped_by_id.values()))
                elif len(set(clamped_by_id.values())) == 1:
                    vals['max_registrations'] = next(iter(clamped_by_id.values()))
                else:
                    # Different plan caps across records — write one by one
                    other = {k: v for k, v in vals.items() if k != 'max_registrations'}
                    for tournament in self:
                        row = dict(other)
                        if tournament.id in clamped_by_id:
                            row['max_registrations'] = clamped_by_id[tournament.id]
                        else:
                            row['max_registrations'] = req
                        super(AuctionTournament, tournament).write(row)
                    return True

        # When linking a SaaS account, also clamp an existing over-limit value
        if 'saas_account_id' in vals and vals.get('saas_account_id'):
            owner = self.env['ac.saas.account'].browse(vals['saas_account_id'])
            if owner.plan_id and 'max_registrations' not in vals:
                for tournament in self:
                    capped = tournament._saas_clamp_max_registrations(
                        tournament.max_registrations, owner.plan_id
                    )
                    if capped != tournament.max_registrations:
                        vals['max_registrations'] = capped
                        break

        # SaaS organisers (all plans) own their tournaments. auction_module.write()
        # blocks non-admins from fields like team_ids — bypass after ownership check.
        if account and not self.env.su:
            if 'active' in vals and not vals.get('active'):
                self._saas_assert_can_archive_or_delete()
            for tournament in self:
                if tournament.saas_account_id and tournament.saas_account_id != account:
                    raise AccessError(_(
                        'You cannot modify tournament "%(name)s" — it belongs to another account.'
                    ) % {'name': tournament.name})
            unclaimed = self.filtered(lambda t: not t.saas_account_id)
            if unclaimed:
                super(AuctionTournament, unclaimed.sudo()).write(
                    {'saas_account_id': account.id}
                )

            if 'team_ids' in vals:
                new_cmds = [c for c in (vals.get('team_ids') or []) if c and c[0] == 0]
                if new_cmds:
                    plan = account.get_plan()
                    for tournament in self:
                        current = len(tournament.team_ids)
                        if current + len(new_cmds) > plan.max_teams_per_tournament:
                            raise ValidationError(_(
                                'Your %(plan)s plan allows up to %(max)s team(s) per tournament.'
                            ) % {
                                'plan': plan.name,
                                'max': plan.max_teams_per_tournament,
                            })

            return super(AuctionTournament, self.sudo()).write(vals)

        return super().write(vals)

    def _saas_assert_can_archive_or_delete(self):
        """SaaS organisers may manage their tournaments but not archive/delete them."""
        user = self.env.user
        if self.env.su:
            return
        if user.has_group('ac_saas_manager.group_saas_manager'):
            return
        if user.has_group('auction_module.group_auction_group_admin'):
            return
        if user.has_group('ac_saas_manager.group_saas_account_user'):
            raise AccessError(_(
                'SaaS organisers cannot archive or delete tournaments. '
                'Please contact AuctionChamp support if you need a tournament removed.'
            ))

    def _assert_can_deactivate_tournament(self):
        self._saas_assert_can_archive_or_delete()
        return super()._assert_can_deactivate_tournament()

    def action_deactivate_tournament(self):
        self._saas_assert_can_archive_or_delete()
        return super().action_deactivate_tournament()

    def unlink(self):
        self._saas_assert_can_archive_or_delete()
        return super().unlink()

    @api.constrains('saas_account_id', 'player_display_template',
                    'player_appearance_algorithm', 'max_registrations')
    def _check_saas_plan_constraints(self):
        for tournament in self:
            account = tournament.saas_account_id
            if not account:
                continue
            plan = account.plan_id
            if not plan:
                continue
            if tournament.player_display_template:
                plan.assert_template_allowed(tournament.player_display_template)
            plan.assert_random_mode_allowed(tournament.player_appearance_algorithm)
            max_p = int(plan.max_players_per_tournament or 0)
            max_reg = int(tournament.max_registrations or 0)
            if max_p and (max_reg <= 0 or max_reg > max_p):
                raise ValidationError(_(
                    'Max registrations must be between 1 and %(max)s on the %(plan)s plan '
                    '(unlimited is not available).'
                ) % {
                    'plan': plan.name,
                    'max': max_p,
                })

    @api.model
    def _saas_repair_max_registrations(self):
        """Clamp existing SaaS tournaments that exceed (or unset) plan registration caps."""
        tournaments = self.sudo().search([('saas_account_id', '!=', False)])
        for tournament in tournaments:
            plan = tournament.saas_account_id.plan_id
            if not plan:
                continue
            capped = tournament._saas_clamp_max_registrations(
                tournament.max_registrations, plan
            )
            if capped != tournament.max_registrations:
                # Bypass re-entrancy noise; constraint expects clamped value
                super(AuctionTournament, tournament).write({
                    'max_registrations': capped,
                })
        return True
