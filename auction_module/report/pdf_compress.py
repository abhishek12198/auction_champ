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

import logging
import os
import subprocess
import tempfile

from odoo import models

_logger = logging.getLogger(__name__)

# Report names that should have Ghostscript PDF compression applied
_PLAYER_CARD_REPORT_NAMES = {
    'auction_module.report_player_card_list',
    'auction_module.report_player_card_list_butterscotch',
    'auction_module.report_player_card_list_strawberry',
    'auction_module.report_player_card_list_cherry',
    'auction_module.report_player_card_list_pistah',
    'auction_module.report_player_card_football_list',
}


class IrActionsReportCompress(models.Model):
    """Extend ir.actions.report to apply Ghostscript PDF compression for player card reports."""
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, res_ids=None, data=None):
        pdf_content, content_type = super()._render_qweb_pdf(res_ids=res_ids, data=data)
        if content_type == 'pdf' and self.report_name in _PLAYER_CARD_REPORT_NAMES:
            try:
                compressed = _compress_pdf_ghostscript(pdf_content)
                if compressed and len(compressed) < len(pdf_content):
                    reduction = (1 - len(compressed) / len(pdf_content)) * 100
                    _logger.info(
                        'Player card PDF compressed: %.1fMB → %.1fMB (%.0f%% smaller)',
                        len(pdf_content) / 1048576,
                        len(compressed) / 1048576,
                        reduction,
                    )
                    pdf_content = compressed
            except Exception:
                _logger.warning('PDF Ghostscript compression failed, returning original.', exc_info=True)
        return pdf_content, content_type


def _compress_pdf_ghostscript(pdf_bytes):
    """Run Ghostscript on pdf_bytes and return the compressed result.

    Tuned for bulk player-card PDFs: keep photos readable while shrinking
    wkhtmltopdf's heavy gradient/shadow raster layers. Target ~print-screen
    quality (~96 DPI colour) so ~80 cards stay well under ~10MB.
    Returns None on any error so the caller can fall back to the original.
    """
    in_fd, in_path = tempfile.mkstemp(suffix='.pdf', prefix='ac_card_in_')
    out_fd, out_path = tempfile.mkstemp(suffix='.pdf', prefix='ac_card_out_')
    try:
        os.write(in_fd, pdf_bytes)
        os.close(in_fd)
        in_fd = None
        os.close(out_fd)
        out_fd = None

        result = subprocess.run(
            [
                'gs',
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.5',
                '-dDetectDuplicateImages=true',
                '-dPDFSETTINGS=/screen',
                '-dDownsampleColorImages=true',
                '-dColorImageResolution=96',
                '-dColorImageDownsampleThreshold=1.0',
                '-dDownsampleGrayImages=true',
                '-dGrayImageResolution=96',
                '-dDownsampleMonoImages=true',
                '-dMonoImageResolution=120',
                '-dAutoFilterColorImages=false',
                '-dColorImageFilter=/DCTEncode',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-sOutputFile=' + out_path,
                '-c',
                '<< /ColorImageDict << /QFactor 0.5 /Blend 1 '
                '/HSamples [2 1 1 2] /VSamples [2 1 1 2] >> >> setdistillerparams',
                '-f',
                in_path,
            ],
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            _logger.warning('Ghostscript exited %d: %s', result.returncode, result.stderr.decode(errors='replace'))
            return None

        with open(out_path, 'rb') as f:
            return f.read()

    finally:
        if in_fd is not None:
            os.close(in_fd)
        if out_fd is not None:
            os.close(out_fd)
        for path in (in_path, out_path):
            try:
                os.unlink(path)
            except OSError:
                pass
