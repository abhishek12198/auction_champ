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
