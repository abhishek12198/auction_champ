# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — tournament share opens one WhatsApp message
#
##############################################################################
from odoo import models


class AuctionWhatsappShareWizard(models.TransientModel):
    _inherit = 'auction.whatsapp.share.wizard'

    def action_share_whatsapp_text(self):
        """Open WhatsApp Web with the full invitation (poster + register links in text)."""
        self.ensure_one()
        tournament = self.tournament_id
        if tournament and hasattr(tournament, '_ac_wa_invitation_message'):
            message = tournament._ac_wa_invitation_message()
            url = tournament._ac_wa_invitation_url(message)
        else:
            message = self.message or ''
            url = self.whatsapp_url or ''
            if message and not url:
                from urllib.parse import quote
                url = 'https://web.whatsapp.com/send?text={}'.format(quote(message, safe=''))
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }
