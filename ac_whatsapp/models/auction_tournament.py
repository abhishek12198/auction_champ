# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — tournament invitation share
#
##############################################################################
from urllib.parse import quote

from odoo import models, _


class AuctionTournament(models.Model):
    _inherit = 'auction.tournament'

    def _ac_wa_poster_public_url(self):
        """Absolute public URL for the tournament poster (no login required)."""
        self.ensure_one()
        if not self.poster_image:
            return False
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        db_name = self.env.cr.dbname
        return '{}/{}/auction/public/image/auction.tournament/{}/poster_image'.format(
            base, db_name, self.id,
        )

    def _ac_wa_invitation_caption(self):
        """Caption for Cloud API image message (poster is the attachment)."""
        self.ensure_one()
        lines = [
            '🏆 You\'re invited!',
            '',
            '{}'.format(self.name or 'Tournament'),
        ]
        if self.description:
            desc = (self.description or '').strip()
            if len(desc) > 280:
                desc = desc[:277] + '...'
            lines.extend(['', desc])

        date_label = self.format_tournament_dates(fmt='%d %B %Y')
        if date_label:
            lines.extend(['', '📅 Date: {}'.format(date_label)])

        if self.venue:
            lines.extend(['', '📍 Venue: {}'.format(self.venue.strip())])

        reg_url = (self.registration_url or '').strip()
        if reg_url:
            lines.extend(['', '📝 Register here:', reg_url])

        if self.whatsapp_group_link:
            lines.extend([
                '',
                '💬 Players WhatsApp Group:',
                self.whatsapp_group_link.strip(),
            ])

        lines.extend(['', '— AuctionChamp'])
        return '\n'.join(lines)[:1024]

    def _ac_wa_invitation_message(self):
        """Text-only fallback for WhatsApp Web (includes poster URL)."""
        self.ensure_one()
        body = self._ac_wa_invitation_caption()
        poster_url = self._ac_wa_poster_public_url()
        if poster_url:
            return '🖼️ Tournament Poster:\n{}\n\n{}'.format(poster_url, body)[:4000]
        return body

    def _ac_wa_invitation_url(self, message=None):
        self.ensure_one()
        text = message if message is not None else self._ac_wa_invitation_message()
        return 'https://web.whatsapp.com/send?text={}'.format(quote(text, safe=''))

    def action_ac_wa_share_invitation(self):
        """Open invite wizard: send poster + caption via WhatsApp Business API."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Share on WhatsApp'),
            'res_model': 'ac.whatsapp.tournament.invite.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tournament_id': self.id,
            },
        }
