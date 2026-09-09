# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — send tournament invitation via Cloud API
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AcWhatsappTournamentInviteWizard(models.TransientModel):
    _name = 'ac.whatsapp.tournament.invite.wizard'
    _description = 'Send Tournament Invite via WhatsApp Business API'

    tournament_id = fields.Many2one(
        'auction.tournament', required=True, readonly=True,
    )
    poster_image = fields.Binary(
        related='tournament_id.poster_image', readonly=True,
    )
    phone_numbers = fields.Text(
        string='Recipient mobile numbers',
        required=True,
        help='One number per line (or comma-separated). '
             '10-digit Indian numbers get +91 automatically unless you include a country code.',
    )
    caption = fields.Text(
        string='Message caption',
        required=True,
        help='Sent as the WhatsApp image caption (with the poster) or as a text message.',
    )
    api_configured = fields.Boolean(compute='_compute_api_configured')
    result_log = fields.Text(string='Result', readonly=True)

    @api.depends_context('uid')
    def _compute_api_configured(self):
        configured = self.env['ac.whatsapp.api'].is_configured()
        for wiz in self:
            wiz.api_configured = configured

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tid = self.env.context.get('default_tournament_id') or self.env.context.get('active_id')
        if tid:
            tournament = self.env['auction.tournament'].browse(tid)
            res['tournament_id'] = tournament.id
            if 'caption' in fields_list or not fields_list:
                res['caption'] = tournament._ac_wa_invitation_caption()
        return res

    def _parse_phones(self):
        self.ensure_one()
        raw = (self.phone_numbers or '').replace(',', '\n').replace(';', '\n')
        phones = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                phones.append(line)
        if not phones:
            raise UserError(_('Enter at least one mobile number.'))
        return phones

    def action_send_via_api(self):
        self.ensure_one()
        Api = self.env['ac.whatsapp.api']
        if not Api.is_configured():
            raise UserError(_(
                'Configure WhatsApp first:\n'
                'Settings → WhatsApp (Twilio Account SID / Auth Token / From number).'
            ))
        if not self.tournament_id.poster_image:
            raise UserError(_(
                'Upload a tournament poster first (Registration tab), '
                'then send the invitation.'
            ))

        phones = self._parse_phones()
        caption = (self.caption or '').strip()
        ok, failed = [], []
        for phone in phones:
            try:
                result = Api.send_tournament_invitation(
                    self.tournament_id, phone, caption=caption,
                )
                ok.append('%s → %s' % (phone, result.get('message_id') or 'sent'))
            except UserError as exc:
                failed.append('%s → %s' % (phone, exc.args[0] if exc.args else str(exc)))
            except Exception as exc:
                failed.append('%s → %s' % (phone, str(exc)))

        lines = []
        if ok:
            lines.append(_('Sent (%s):') % len(ok))
            lines.extend(ok)
        if failed:
            if lines:
                lines.append('')
            lines.append(_('Failed (%s):') % len(failed))
            lines.extend(failed)
        self.result_log = '\n'.join(lines)

        if not ok and failed:
            raise UserError(_('Could not send any messages:\n%s') % '\n'.join(failed))

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_whatsapp_web(self):
        """Fallback: open WhatsApp Web with text (no native image attach)."""
        self.ensure_one()
        tournament = self.tournament_id
        message = self.caption or tournament._ac_wa_invitation_message()
        return {
            'type': 'ir.actions.act_url',
            'url': tournament._ac_wa_invitation_url(message),
            'target': 'new',
        }
