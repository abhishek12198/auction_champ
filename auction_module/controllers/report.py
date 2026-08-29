# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
##############################################################################

import json
import logging

from odoo import http
from odoo.addons.web.controllers.main import ReportController, content_disposition
from odoo.http import request

_logger = logging.getLogger(__name__)

_PLAYER_CARD_REPORT_NAMES = frozenset({
    'auction_module.report_player_card_list',
    'auction_module.report_player_card_list_butterscotch',
    'auction_module.report_player_card_list_strawberry',
    'auction_module.report_player_card_list_cherry',
    'auction_module.report_player_card_list_pistah',
    'auction_module.report_player_card_list_lemon',
    'auction_module.report_player_card_list_blackberry',
    'auction_module.report_player_card_football_list',
})


class AuctionPlayerCardReportController(ReportController):
    """Ensure bulk Print Player Cards PDFs use the tier-aware download filename.

    Odoo core only evaluates ``print_report_name`` for a single record; multi-
    select otherwise downloads as ``Player Card.pdf``.
    """

    @http.route(['/report/download'], type='http', auth="user")
    def report_download(self, data, context=None):
        response = super().report_download(data, context=context)
        try:
            if not response or getattr(response, 'status_code', 200) >= 400:
                return response
            requestcontent = json.loads(data)
            url = requestcontent[0]
            if not url.startswith('/report/pdf/'):
                return response
            reportname = url.split('/report/pdf/')[1].split('?')[0]
            docids = None
            if '/' in reportname:
                reportname, docids = reportname.split('/')
            if reportname not in _PLAYER_CARD_REPORT_NAMES or not docids:
                return response
            report = request.env['ir.actions.report']._get_report_from_name(reportname)
            if not report or report.model != 'auction.team.player':
                return response
            ids = [int(x) for x in docids.split(',') if x]
            players = request.env['auction.team.player'].browse(ids).exists()
            if not players:
                return response
            filename = '%s.pdf' % players.get_player_cards_print_filename()
            response.headers['Content-Disposition'] = content_disposition(filename)
        except Exception:
            _logger.exception('Could not set player-card download filename')
        return response
