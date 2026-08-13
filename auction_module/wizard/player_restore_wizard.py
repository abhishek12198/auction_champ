# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

from odoo import fields, models


class AuctionTeamPlayerRestoreWizard(models.TransientModel):
    _name = 'auction.team.player.restore.wizard'
    _description = 'Confirm Restore Deleted Player'

    deleted_player_ids = fields.Many2many(
        'auction.team.player.deleted',
        'ac_player_restore_wiz_rel',
        'wizard_id',
        'deleted_id',
        string='Players to Restore',
        readonly=True,
    )
    warning_html = fields.Html(
        string='Warning',
        readonly=True,
        sanitize=False,
    )

    def action_confirm_restore(self):
        self.ensure_one()
        if not self.deleted_player_ids:
            return {'type': 'ir.actions.act_window_close'}
        return self.deleted_player_ids.with_context(
            skip_restore_duplicate_warning=True,
            restore_from_tournament=self.env.context.get('restore_from_tournament'),
        )._do_restore_players()
