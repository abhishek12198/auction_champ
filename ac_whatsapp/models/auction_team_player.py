# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — player fields + confirmation helpers
#
##############################################################################
import base64
import logging
import secrets
from urllib.parse import quote

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AuctionTeamPlayer(models.Model):
    _inherit = 'auction.team.player'

    email = fields.Char(
        string='Email',
        help='Optional. Used to email the player-card PDF after registration.',
    )
    card_access_token = fields.Char(
        string='Card Access Token',
        copy=False,
        index=True,
        default=lambda self: secrets.token_urlsafe(24),
        help='Secret token required to download the player card via public link.',
    )
    registration_confirm_sent = fields.Boolean(
        string='Registration Confirm Sent',
        default=False,
        copy=False,
        help='True after the registration confirmation email was attempted.',
    )
    registration_whatsapp_sent = fields.Boolean(
        string='Registration WhatsApp Sent',
        default=False,
        copy=False,
        help='True after a registration confirmation WhatsApp message was sent.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('card_access_token'):
                vals['card_access_token'] = secrets.token_urlsafe(24)
        return super().create(vals_list)

    def _ac_wa_normalize_phone(self):
        """Return digits-only mobile suitable for wa.me (best-effort)."""
        self.ensure_one()
        return ''.join(ch for ch in (self.contact or '') if ch.isdigit())

    def _ac_wa_card_url(self, db_name=None):
        """Absolute secure PDF URL for this player."""
        self.ensure_one()
        if not self.card_access_token:
            self.sudo().write({'card_access_token': secrets.token_urlsafe(24)})
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        db_name = db_name or self.env.cr.dbname
        return '{}/{}/player/card/{}?token={}'.format(
            base, db_name, self.id, self.card_access_token,
        )

    def _ac_wa_confirmation_message(self, db_name=None):
        """Plain-text registration confirmation (no buttons / templates)."""
        self.ensure_one()
        tournament_name = (
            self.tournament_id.name if self.tournament_id else 'the tournament'
        )
        serial_number = self.sl_no or '—'
        return (
            '🎉 Registration Successful\n'
            '\n'
            'Thank you for registering for {tournament_name}.\n'
            '\n'
            'Your registration has been confirmed successfully.\n'
            '\n'
            'Registration Serial Number: {serial_number}\n'
            '\n'
            'Kindly retain this serial number for verification and future communication.\n'
            '\n'
            'We look forward to seeing you at the tournament. Best of luck!'
        ).format(
            tournament_name=tournament_name,
            serial_number=serial_number,
        )

    def _ac_wa_share_url(self, db_name=None):
        """WhatsApp URL with confirmation text (prefills chat to player mobile)."""
        self.ensure_one()
        text = self._ac_wa_confirmation_message(db_name=db_name)
        phone = self._ac_wa_normalize_phone()
        encoded = quote(text)
        if phone:
            return 'https://api.whatsapp.com/send?phone={}&text={}'.format(phone, encoded)
        return 'https://api.whatsapp.com/send?text={}'.format(encoded)

    def action_ac_wa_send_registration_whatsapp(self, db_name=None):
        """Send registration confirmation to the player's WhatsApp (Twilio / Meta)."""
        Api = self.env['ac.whatsapp.api']
        for player in self:
            contact = (player.contact or '').strip()
            if not contact:
                _logger.info(
                    'ac_whatsapp: skip WhatsApp confirm — no mobile for player %s',
                    player.id,
                )
                continue
            if not Api.is_configured():
                _logger.warning(
                    'ac_whatsapp: WhatsApp API not configured; skip player %s',
                    player.id,
                )
                continue
            try:
                Api.send_registration_confirmation(contact, player, db_name=db_name)
                player.sudo().write({'registration_whatsapp_sent': True})
                _logger.info(
                    'ac_whatsapp: registration WhatsApp sent for player %s',
                    player.id,
                )
            except Exception:
                _logger.exception(
                    'Failed to send registration WhatsApp for player %s',
                    player.id,
                )
        return True

    def _ac_wa_maybe_send_registration_whatsapp(self, db_name=None):
        """Auto-send if enabled in settings and not already sent."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ac_whatsapp.auto_send_registration')
        if raw in (None, False, ''):
            enabled = True  # default on until explicitly disabled
        else:
            enabled = str(raw).strip().lower() in ('1', 'true', 'yes', 'y', 'on')
        if not enabled:
            return False
        players = self.filtered(
            lambda p: p.exists()
            and (p.contact or '').strip()
            and not p.registration_whatsapp_sent
        )
        if not players:
            return False
        return players.action_ac_wa_send_registration_whatsapp(db_name=db_name)

    def _ac_wa_render_card_pdf(self):
        """Return (pdf_bytes, filename) for this player's themed card."""
        self.ensure_one()
        tournament = self.tournament_id
        if self.photo and not self.photo_card:
            self._compute_photo_card()
            self.flush(['photo_card'])
        if tournament and tournament.logo and not tournament.logo_card:
            tournament._compute_logo_card()
            tournament.flush(['logo_card'])

        theme = (tournament.player_display_template or 'vanilla') if tournament else 'vanilla'
        if tournament and tournament.tournament_type == 'football':
            report_ref = 'auction_module.action_report_player_card_football'
        else:
            report_map = {
                'vanilla': 'auction_module.action_report_player_card',
                'butterscotch': 'auction_module.action_report_player_card_butterscotch',
                'strawberry': 'auction_module.action_report_player_card_strawberry',
                'cherry': 'auction_module.action_report_player_card_cherry',
                'pistah': 'auction_module.action_report_player_card_pistah',
                'lemon': 'auction_module.action_report_player_card_lemon',
            }
            report_ref = report_map.get(theme, 'auction_module.action_report_player_card')

        report = self.env.ref(report_ref).sudo().with_context(skip_player_card_compress=True)
        pdf_content, _ = report._render_qweb_pdf([self.id])
        safe_name = ''.join(
            ch if ch.isalnum() or ch in ('-', '_') else '_'
            for ch in (self.name or 'player')
        )[:40]
        return pdf_content, 'player_card_%s.pdf' % safe_name

    def action_ac_wa_send_registration_email(self):
        """Email confirmation + player-card PDF when email is set."""
        Mail = self.env['mail.mail'].sudo()
        Attachment = self.env['ir.attachment'].sudo()
        for player in self:
            email = (player.email or '').strip()
            if not email:
                continue
            try:
                pdf_content, filename = player._ac_wa_render_card_pdf()
                card_url = player._ac_wa_card_url()
                attachment = Attachment.create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'mimetype': 'application/pdf',
                    # Do not bind to the player: that makes mail.message inherit
                    # tournament/SaaS record rules and can block attachment read
                    # during send for non-superuser admins.
                })
                body = _(
                    '<p>Hi %(name)s,</p>'
                    '<p>You are registered for <strong>%(tournament)s</strong>. '
                    'Your profile is under review.</p>'
                    '<p>Your player card PDF is attached. '
                    'You can also download it securely here:<br/>'
                    '<a href="%(url)s">%(url)s</a></p>'
                    '<p>— AuctionChamp</p>'
                ) % {
                    'name': player.name or 'Player',
                    'tournament': player.tournament_id.name or 'the tournament',
                    'url': card_url,
                }
                Mail.create({
                    'subject': _('Registration confirmed — %s') % (
                        player.tournament_id.name or 'AuctionChamp'
                    ),
                    'body_html': body,
                    'email_to': email,
                    'attachment_ids': [(4, attachment.id)],
                    'auto_delete': True,
                }).send()
                player.sudo().write({'registration_confirm_sent': True})
            except Exception:
                _logger.exception(
                    'Failed to email registration confirmation for player %s',
                    player.id,
                )
        return True
