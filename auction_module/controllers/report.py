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
from odoo.http import content_disposition, request
from odoo.addons.web.controllers.main import ReportController

_logger = logging.getLogger(__name__)


class AuctionReportController(ReportController):
    """Fix player-card PDF filenames when printing multiple players at once."""

    @http.route(['/report/download'], type='http', auth='user')
    def report_download(self, data, context=None):
        docids = None
        reportname = None
        extension = 'pdf'
        try:
            requestcontent = json.loads(data)
            url, report_type = requestcontent[0], requestcontent[1]
            if report_type in ('qweb-pdf', 'qweb-text'):
                extension = 'pdf' if report_type == 'qweb-pdf' else 'txt'
                pattern = '/report/pdf/' if report_type == 'qweb-pdf' else '/report/text/'
                reportname = url.split(pattern)[1].split('?')[0]
                if '/' in reportname:
                    reportname, docids = reportname.split('/', 1)
        except Exception:
            docids = None
            reportname = None

        response = super(AuctionReportController, self).report_download(data, context=context)

        try:
            if docids and reportname and getattr(response, 'status_code', None) == 200:
                report = request.env['ir.actions.report']._get_report_from_name(reportname)
                if report and report._is_player_card_report():
                    ids = [int(x) for x in docids.split(',') if x.strip()]
                    filename = report.get_download_filename(ids, extension)
                    response.headers.set('Content-Disposition', content_disposition(filename))
        except Exception:
            _logger.exception('Failed to set player card report filename')

        return response
