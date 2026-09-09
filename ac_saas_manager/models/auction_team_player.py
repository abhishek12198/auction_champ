# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — player registration cap per tournament
#
##############################################################################
from odoo import api, models


class AuctionTeamPlayer(models.Model):
    _inherit = 'auction.team.player'

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
        Account = self.env['ac.saas.account']
        result = self.browse()
        for vals in vals_list:
            vals = dict(vals)
            # Prefer tournament ownership even for public / sudo creates
            tournament = False
            tid = vals.get('tournament_id') or self.env.context.get('default_tournament_id')
            if tid:
                tournament = self.env['auction.tournament'].sudo().browse(tid)

            account = Account._get_account_for_user()
            if not account and tournament and tournament.saas_account_id:
                account = tournament.saas_account_id

            if tournament:
                Account.assert_tournament_not_frozen(
                    tournament, operation='register or update players'
                )

            if account:
                Account.assert_env_not_frozen(operation='register or update players')
                # Re-check after env (covers non-sudo path); tournament covers sudo
                account.assert_not_frozen(operation='register or update players')
                tournament = self.env['auction.tournament']._saas_prepare_for_account(
                    account, tid
                )
                if not vals.get('icon_player') and not self.env.context.get('saas_skip_quota_check'):
                    account.assert_can_add_player(tournament)
                vals['tournament_id'] = tournament.id
                self._ensure_default_tier_vals(vals)
                result |= super(AuctionTeamPlayer, self.sudo()).create([vals])
            else:
                self._ensure_default_tier_vals(vals)
                result |= super().create([vals])
        return result

    def write(self, vals):
        Account = self.env['ac.saas.account']
        # Live-auction flags (stage / mystery reveal) must not be blocked by
        # freeze checks when the write is only those fields — otherwise clearing
        # another tenant's leftover on-stage row (or stamp cleanup) breaks Roll
        # Call + projector. Real mutations (sell, create, etc.) still freeze.
        runtime_only = set(vals) <= {'is_on_stage', 'mystery_revealed'}
        if not runtime_only:
            Account.assert_env_not_frozen(operation='update players')
            for player in self:
                Account.assert_tournament_not_frozen(
                    player.tournament_id, operation='update players'
                )
        return super().write(vals)

    def unlink(self):
        Account = self.env['ac.saas.account']
        Account.assert_env_not_frozen(operation='delete players')
        for player in self:
            Account.assert_tournament_not_frozen(
                player.tournament_id, operation='delete players'
            )
        return super().unlink()
