# -*- coding: utf-8 -*-
import base64
import io
import zipfile

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AuctionPdfToPng(models.TransientModel):
    _name = 'auction.pdf.to.png'
    _description = 'Convert Player Card PDF to PNG Images'

    state = fields.Selection([('draft', 'Upload'), ('done', 'Done')], default='draft')
    pdf_file = fields.Binary(string='Player Cards PDF', required=True)
    pdf_filename = fields.Char(string='PDF Filename')
    tournament_id = fields.Many2one(
        'auction.tournament', string='Tournament',
        default=lambda self: self.env['auction.tournament'].search(
            [('active', '=', True)], limit=1),
        help='Select the tournament to use player serial numbers as image names. '
             'Leave blank to name images by page number.'
    )
    zip_file = fields.Binary(string='Download ZIP', readonly=True)
    zip_filename = fields.Char(default='player_cards.zip')
    page_count = fields.Integer(string='Pages Converted', readonly=True)

    def action_convert(self):
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(_('Please upload a PDF file first.'))

        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise UserError(_(
                'PyMuPDF library is not installed. '
                'Please run: pip install PyMuPDF'
            ))

        # ── Load players ordered by sl_no (for naming) ──────────────────
        player_sl_map = {}
        if self.tournament_id:
            players = self.env['auction.team.player'].search(
                [('tournament_id', '=', self.tournament_id.id)],
                order='sl_no asc'
            )
            for idx, p in enumerate(players):
                player_sl_map[idx] = str(p.sl_no)

        # ── Convert PDF pages → PNG ──────────────────────────────────────
        pdf_bytes = base64.b64decode(self.pdf_file)
        try:
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        except Exception as e:
            raise UserError(_('Failed to open PDF: %s') % str(e))

        zip_buffer = io.BytesIO()
        count = len(doc)

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(doc):
                # 2× scale → 192 DPI — good quality for print-size cards
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes('png')

                # Name by player sl_no if available, else by 1-based page number
                if player_sl_map.get(i):
                    filename = f'{player_sl_map[i]}.png'
                else:
                    filename = f'{i + 1}.png'

                zf.writestr(filename, img_bytes)

        doc.close()
        zip_data = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')

        self.write({
            'zip_file': zip_data,
            'zip_filename': 'player_cards.zip',
            'page_count': count,
            'state': 'done',
        })

        # Reopen the same wizard record to show the download section
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'auction.pdf.to.png',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_reset(self):
        """Start over with a fresh upload."""
        self.write({
            'pdf_file': False,
            'pdf_filename': False,
            'zip_file': False,
            'page_count': 0,
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'auction.pdf.to.png',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
