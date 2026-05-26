# -*- coding: utf-8 -*-
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

    Uses /ebook preset (≈150 DPI images) which is a good balance between
    quality and file size for digital player cards.
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
                '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/ebook',
                '-dColorImageResolution=150',
                '-dGrayImageResolution=150',
                '-dMonoImageResolution=150',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-sOutputFile=' + out_path,
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
