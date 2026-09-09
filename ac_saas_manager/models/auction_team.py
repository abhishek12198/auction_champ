# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — team cap per tournament
#
##############################################################################
from odoo import api, models


class AuctionTeam(models.Model):
    _inherit = 'auction.team'

    @api.model
    def _saas_default_tournament_id(self, account):
        """Active navbar tournament if owned by account, else first account tournament."""
        if not account:
            return False
        account_ids = account.sudo().tournament_ids.ids
        if not account_ids:
            return False
        active = self.env.user.sudo().get_working_tournament()
        if active and active.id in account_ids:
            return active.id
        return account_ids[0]

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if defaults.get('tournament_id'):
            return defaults
        account = self.env['ac.saas.account']._get_account_for_user()
        tid = self._saas_default_tournament_id(account)
        if tid:
            defaults['tournament_id'] = tid
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        account = self.env['ac.saas.account']._get_account_for_user()
        if not account:
            return super().create(vals_list)

        account.assert_not_frozen(operation='create teams')
        result = self.browse()
        for vals in vals_list:
            vals = dict(vals)
            # Prefer explicit / context tournament; never silently pin to first tournament
            tid = vals.get('tournament_id') or self.env.context.get('default_tournament_id')
            tournament = self.env['auction.tournament']._saas_prepare_for_account(
                account, tid
            )
            self.env['ac.saas.account'].assert_tournament_not_frozen(
                tournament, operation='create teams'
            )
            if not self.env.context.get('saas_skip_quota_check'):
                account.assert_can_add_team(tournament)
            vals['tournament_id'] = tournament.id
            # Ownership validated — sudo bypasses legacy tournament_ids rules
            result |= super(AuctionTeam, self.sudo()).create([vals])
        return result
