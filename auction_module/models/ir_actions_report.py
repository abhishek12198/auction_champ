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
import logging
import re
import time

from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

PLAYER_CARD_REPORT_NAMES = frozenset({
    'auction_module.report_player_card_list',
    'auction_module.report_player_card_list_butterscotch',
    'auction_module.report_player_card_list_strawberry',
    'auction_module.report_player_card_list_cherry',
    'auction_module.report_player_card_list_pistah',
    'auction_module.report_player_card_list_lemon',
    'auction_module.report_player_card_list_blackberry',
    'auction_module.report_player_card_football_list',
})


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _is_player_card_report(self):
        self.ensure_one()
        return self.report_name in PLAYER_CARD_REPORT_NAMES

    @staticmethod
    def _safe_filename_part(text, fallback=''):
        """Sanitize one filename segment; keep spaces for readable download names."""
        text = ' '.join((text or '').split())
        text = re.sub(r'[\\/:*?"<>|]+', '', text)
        return text.strip() or fallback

    def _player_card_download_basename(self, players):
        """Build PDF basename from tournament, short description, and selection."""
        players = players.exists()
        if not players:
            return 'Players'

        tournament = players[0].tournament_id
        parts = []
        if tournament:
            if tournament.name:
                parts.append(self._safe_filename_part(tournament.name, 'Tournament'))
            if tournament.description:
                parts.append(self._safe_filename_part(tournament.description))

        if len(players) == 1:
            parts.append(self._safe_filename_part(players[0].name, 'Player'))
        else:
            parts.append('Players')
            tier_groups = {p.tier_id.id if p.tier_id else False for p in players}
            if len(tier_groups) == 1:
                tier = players[0].tier_id
                if tier and tier.name:
                    parts.append(self._safe_filename_part(tier.name))

        return ' '.join(part for part in parts if part)

    def get_download_filename(self, docids, extension='pdf'):
        """Download filename (with extension) for report downloads."""
        self.ensure_one()
        if isinstance(docids, str):
            ids = [int(x) for x in docids.split(',') if x.strip()]
        else:
            ids = [int(x) for x in (docids or []) if x]
        if not ids:
            return '%s.%s' % (self.name, extension)
        obj = self.env[self.model].browse(ids).exists()
        if self._is_player_card_report() and obj:
            base = self._player_card_download_basename(obj)
            return '%s.%s' % (base, extension)
        if self.print_report_name and len(obj) == 1:
            try:
                report_name = safe_eval(
                    self.print_report_name, {'object': obj, 'time': time}
                )
                if report_name:
                    return '%s.%s' % (report_name, extension)
            except Exception:
                _logger.exception(
                    'print_report_name failed for report %s', self.report_name
                )
        return '%s.%s' % (self.name, extension)

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
            'auction_module.report_player_card_list_blackberry',
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
