# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — Mystery tier gated by plan
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AuctionPlayerTier(models.Model):
    _inherit = 'auction.player.tier'

    saas_allow_mystery = fields.Boolean(
        string='Plan Allows Mystery',
        compute='_compute_saas_allow_mystery',
        help='True when the tournament SaaS plan (or current account plan) '
             'includes Mystery players. Admins without a SaaS account always see Mystery.',
    )

    @api.depends(
        'tournament_id',
        'tournament_id.saas_account_id',
        'tournament_id.saas_account_id.plan_id',
        'tournament_id.saas_account_id.plan_id.allow_mystery_players',
    )
    def _compute_saas_allow_mystery(self):
        Account = self.env['ac.saas.account']
        for tier in self:
            account = False
            if tier.tournament_id and tier.tournament_id.saas_account_id:
                account = tier.tournament_id.saas_account_id
            if not account:
                account = Account._get_account_for_user()
            if not account or not account.plan_id:
                # No SaaS account (admin / legacy) → keep Mystery available
                tier.saas_allow_mystery = True
            else:
                tier.saas_allow_mystery = bool(account.plan_id.allow_mystery_players)

    def _saas_assert_mystery_allowed(self, vals=None):
        """Block enabling Mystery when the plan does not include it."""
        vals = vals or {}
        for tier in self:
            want_mystery = vals.get('mystery', tier.mystery) if vals else tier.mystery
            if not want_mystery:
                continue
            # Recompute for this record's tournament context
            account = False
            tournament = tier.tournament_id
            if vals.get('tournament_id'):
                tournament = self.env['auction.tournament'].browse(vals['tournament_id'])
            if tournament and tournament.saas_account_id:
                account = tournament.saas_account_id
            if not account:
                account = self.env['ac.saas.account']._get_account_for_user()
            if not account or not account.plan_id:
                continue
            account.plan_id.assert_mystery_allowed()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('mystery'):
                # Validate against tournament / current account plan
                tournament = False
                if vals.get('tournament_id'):
                    tournament = self.env['auction.tournament'].browse(vals['tournament_id'])
                account = (
                    tournament.saas_account_id
                    if tournament and tournament.saas_account_id
                    else self.env['ac.saas.account']._get_account_for_user()
                )
                if account and account.plan_id:
                    account.plan_id.assert_mystery_allowed()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('mystery') or ('tournament_id' in vals and any(self.mapped('mystery'))):
            self._saas_assert_mystery_allowed(vals)
        return super().write(vals)

    @api.constrains('mystery', 'tournament_id')
    def _check_saas_mystery_plan(self):
        for tier in self:
            if not tier.mystery:
                continue
            if not tier.saas_allow_mystery:
                plan = (
                    tier.tournament_id.saas_account_id.plan_id
                    if tier.tournament_id and tier.tournament_id.saas_account_id
                    else False
                )
                upgrade = self.env['ac.saas.plan'].get_min_plan_for_mystery()
                raise ValidationError(_(
                    'Mystery players are not included in the %(plan)s plan. '
                    'Upgrade to %(upgrade)s (or higher) to enable Mystery tiers.'
                ) % {
                    'plan': plan.name if plan else _('current'),
                    'upgrade': upgrade.name if upgrade else 'Pro',
                })
