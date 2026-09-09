# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — freeze expired accounts (no create/write/unlink)
#
##############################################################################
from odoo import api, models


class AuctionTournamentSecurityMixin(models.AbstractModel):
    _inherit = 'auction.tournament.security.mixin'

    def _auction_allowed_tournament_ids(self):
        """SaaS scoping (all plans):

        * Tournament master → every tournament on the account
        * Menus (players, teams, …) → badge-selected active tournament
        * Tournament form one2many lines → also allow that form's tournament
        """
        account = self.env['ac.saas.account']._get_account_for_user()
        if not account:
            return super()._auction_allowed_tournament_ids()

        all_ids = account.sudo().tournament_ids.ids
        if not all_ids:
            return [False]

        # Tournament master: full catalogue for this account
        if self._name == 'auction.tournament':
            return all_ids

        allowed = set()
        working = self.env.user.get_working_tournament()
        if working and working.id in all_ids:
            allowed.add(working.id)

        # When editing a tournament form, O2M lines must still load for that record
        # even if the badge points at a different tournament.
        ctx = self.env.context
        form_tid = ctx.get('default_tournament_id')
        if not form_tid and ctx.get('active_model') == 'auction.tournament':
            form_tid = ctx.get('active_id')
        if form_tid in all_ids:
            allowed.add(form_tid)

        return list(allowed) if allowed else [False]

    def _saas_assert_writable(self, operation='change data'):
        self.env['ac.saas.account'].assert_env_not_frozen(operation=operation)

    @api.model_create_multi
    def create(self, vals_list):
        self._saas_assert_writable(operation='create records')
        return super().create(vals_list)

    def write(self, vals):
        self._saas_assert_writable(operation='update records')
        return super().write(vals)

    def unlink(self):
        self._saas_assert_writable(operation='delete records')
        return super().unlink()
