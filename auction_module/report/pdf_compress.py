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

    Tuned for the auction player cards: keeps the player photo and tournament
    logo sharp (colour images ~130 DPI, JPEG QFactor 0.8) while aggressively
    compressing the many rasterised gradient / glassmorphism / shadow layers
    that wkhtmltopdf emits per page, and de-duplicating repeated image objects.
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
                # Merge byte-identical images (logos/backgrounds) into a single object.
                '-dDetectDuplicateImages=true',
                '-dPDFSETTINGS=/ebook',
                # Cap colour images (photos/logos) at ~130 DPI – sharp on the card,
                # but avoids embedding oversized source photos.
                '-dDownsampleColorImages=true',
                '-dColorImageResolution=130',
                '-dColorImageDownsampleThreshold=1.0',
                # Soft-mask / shadow layers are greyscale – downsample harder.
                '-dDownsampleGrayImages=true',
                '-dGrayImageResolution=110',
                '-dDownsampleMonoImages=true',
                '-dMonoImageResolution=150',
                # Force JPEG (DCT) on colour images with an explicit quality factor.
                # QFactor 0.8 keeps photos/logos crisp while compressing the many
                # smooth gradient/glassmorphism panels much smaller.
                '-dAutoFilterColorImages=false',
                '-dColorImageFilter=/DCTEncode',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                '-sOutputFile=' + out_path,
                '-c',
                '<< /ColorImageDict << /QFactor 0.8 /Blend 1 '
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
