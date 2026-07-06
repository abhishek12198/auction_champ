# -*- coding: utf-8 -*-
from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, res_ids=None, data=None):
        """Route football player-card prints to the football paperformat.

        The player-card "Print" menu is bound to ``action_report_player_card``
        (the vanilla report, cricket paperformat). Its QWeb dispatcher already
        renders football content for football players, but on the cricket
        page size, so a football card is a few millimetres too tall and spills
        onto a second page. Whichever entry point triggers the generic card
        report, redirect an all-football batch to the dedicated football report
        action so it uses the football paperformat (one card per page).
        """
        generic_card_reports = (
            'auction_module.report_player_card_list',
            'auction_module.report_player_card_list_butterscotch',
            'auction_module.report_player_card_list_strawberry',
            'auction_module.report_player_card_list_cherry',
            'auction_module.report_player_card_list_pistah',
        )
        if self.report_name in generic_card_reports and res_ids:
            players = self.env['auction.team.player'].browse(res_ids).exists()
            if players and all(
                p.tournament_id.tournament_type == 'football' for p in players
            ):
                football = self.env.ref(
                    'auction_module.action_report_player_card_football',
                    raise_if_not_found=False,
                )
                if football and football.id != self.id:
                    return football._render_qweb_pdf(res_ids=res_ids, data=data)
        return super()._render_qweb_pdf(res_ids=res_ids, data=data)
