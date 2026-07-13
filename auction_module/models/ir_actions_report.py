# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, res_ids=None, data=None):
        """Route football player-card prints to the football report action.

        The player-card "Print" menu is bound to ``action_report_player_card``
        (the vanilla report). Its QWeb dispatcher already renders football
        content for football players; redirect an all-football batch to the
        dedicated football report action so layout stays consistent regardless
        of entry point.
        """
        generic_card_reports = (
            'auction_module.report_player_card_list',
            'auction_module.report_player_card_list_butterscotch',
            'auction_module.report_player_card_list_strawberry',
            'auction_module.report_player_card_list_cherry',
            'auction_module.report_player_card_list_pistah',
            'auction_module.report_player_card_list_lemon',
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
