# -*- coding: utf-8 -*-
import urllib.parse

from odoo import api, fields, models


class WhatsappShareWizard(models.TransientModel):
    _name = 'auction.whatsapp.share.wizard'
    _description = 'WhatsApp Share Wizard'

    tournament_id = fields.Many2one('auction.tournament', required=True, readonly=True)
    poster_image  = fields.Binary(related='tournament_id.poster_image', string='Poster')
    message       = fields.Text(readonly=True)
    whatsapp_url  = fields.Char(readonly=True)

    # ── Share via native share-sheet (mobile) or wa.me (desktop) ─────────────

    def action_share_whatsapp_text(self):
        """Open WhatsApp with the full message pre-filled.

        On mobile: tries navigator.share({text}) via a client action —
        opens the native share sheet so the user can pick WhatsApp.
        Falls back to the wa.me URL on desktop / unsupported browsers.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'auction_module.share_text',
            'params': {
                'message': self.message,
                'wa_url':  self.whatsapp_url,
            },
        }

    # ── Open poster in a new tab (user saves from there) ─────────────────────

    def action_download_poster(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/image/auction.tournament/{}/poster_image'.format(
                self.tournament_id.id
            ),
            'target': 'new',
        }

    # ── Copy message to clipboard ─────────────────────────────────────────────

    def action_copy_message(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'auction_module.copy_to_clipboard',
            'params': {'text': self.message},
        }
