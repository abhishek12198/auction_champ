# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — Meta Cloud API + Twilio WhatsApp client
#
##############################################################################
import base64
import io
import json
import logging
import re

import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GRAPH_VERSION = 'v21.0'

try:
    from twilio.rest import Client as TwilioClient
except ImportError:  # pragma: no cover
    TwilioClient = None


class AcWhatsappApi(models.AbstractModel):
    _name = 'ac.whatsapp.api'
    _description = 'WhatsApp API Client (Twilio / Meta)'

    # ── Provider / config ─────────────────────────────────────────────────

    @api.model
    def get_provider(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return (ICP.get_param('ac_whatsapp.provider') or 'twilio').strip().lower()

    @api.model
    def is_configured(self):
        provider = self.get_provider()
        if provider == 'twilio':
            return self._twilio_is_configured()
        return self._meta_is_configured()

    @api.model
    def normalize_phone(self, phone, default_country_code=None):
        """Return digits-only E.164 without leading +."""
        ICP = self.env['ir.config_parameter'].sudo()
        if default_country_code is None:
            default_country_code = (
                ICP.get_param('ac_whatsapp.default_country_code') or '91'
            ).strip()
        digits = re.sub(r'\D', '', phone or '')
        if not digits:
            raise UserError(_('Please enter a valid mobile number.'))
        if digits.startswith(default_country_code) and len(digits) >= 10 + len(default_country_code):
            return digits
        if len(digits) == 10 and default_country_code:
            return '%s%s' % (default_country_code, digits)
        if digits.startswith('0') and len(digits) == 11 and default_country_code:
            return '%s%s' % (default_country_code, digits[1:])
        return digits

    @api.model
    def _whatsapp_address(self, phone):
        """Twilio WhatsApp address: whatsapp:+E164."""
        digits = self.normalize_phone(phone)
        return 'whatsapp:+%s' % digits

    # ── Public send API (routes by provider) ──────────────────────────────

    @api.model
    def send_text(self, phone, body):
        if self.get_provider() == 'twilio':
            return self._twilio_send_text(phone, body)
        return self._meta_send_text(phone, body)

    @api.model
    def send_registration_confirmation(self, phone, player, db_name=None):
        """
        Send player registration confirmation.
        Twilio: preferred path uses Content Template (content_sid + variables).
        Meta / Twilio fallback: free-form text body.
        """
        if self.get_provider() == 'twilio':
            return self._twilio_send_registration(phone, player, db_name=db_name)
        body = player._ac_wa_confirmation_message(db_name=db_name)
        return self._meta_send_text(phone, body)

    @api.model
    def send_image(self, phone, media_id=None, image_link=None, caption=None):
        if self.get_provider() == 'twilio':
            if not image_link:
                raise UserError(_(
                    'Twilio image messages require a public image URL '
                    '(media_id upload is Meta-only).'
                ))
            return self._twilio_send_media(phone, image_link, body=caption)
        return self._meta_send_image(
            phone, media_id=media_id, image_link=image_link, caption=caption,
        )

    @api.model
    def send_tournament_invitation(self, tournament, phone, caption=None):
        tournament.ensure_one()
        caption = caption if caption is not None else tournament._ac_wa_invitation_caption()
        poster_url = tournament._ac_wa_poster_public_url()
        if self.get_provider() == 'twilio':
            if poster_url:
                return self._twilio_send_media(phone, poster_url, body=caption)
            return self._twilio_send_text(phone, caption)
        if tournament.poster_image:
            media_id = self.upload_tournament_poster(tournament)
            return self._meta_send_image(phone, media_id=media_id, caption=caption)
        return self._meta_send_text(phone, caption)

    # ══════════════════════════════════════════════════════════════════════
    # Twilio
    # ══════════════════════════════════════════════════════════════════════

    @api.model
    def _twilio_is_configured(self):
        ICP = self.env['ir.config_parameter'].sudo()
        sid = (ICP.get_param('ac_whatsapp.twilio_account_sid') or '').strip()
        token = (ICP.get_param('ac_whatsapp.twilio_auth_token') or '').strip()
        from_wa = (ICP.get_param('ac_whatsapp.twilio_from') or '').strip()
        return bool(sid and token and from_wa and TwilioClient is not None)

    @api.model
    def _twilio_client(self):
        if TwilioClient is None:
            raise UserError(_(
                'Python package "twilio" is not installed.\n'
                'Run: pip install twilio'
            ))
        ICP = self.env['ir.config_parameter'].sudo()
        sid = (ICP.get_param('ac_whatsapp.twilio_account_sid') or '').strip()
        token = (ICP.get_param('ac_whatsapp.twilio_auth_token') or '').strip()
        from_wa = (ICP.get_param('ac_whatsapp.twilio_from') or '').strip()
        if not sid or not token or not from_wa:
            raise UserError(_(
                'Twilio WhatsApp is not configured.\n'
                'Go to Settings → WhatsApp and set Account SID, Auth Token, '
                'and From WhatsApp number (e.g. whatsapp:+14155238886).'
            ))
        if not from_wa.startswith('whatsapp:'):
            from_wa = 'whatsapp:+%s' % re.sub(r'\D', '', from_wa)
        return TwilioClient(sid, token), from_wa

    @api.model
    def _twilio_send_text(self, phone, body):
        client, from_wa = self._twilio_client()
        to_wa = self._whatsapp_address(phone)
        try:
            message = client.messages.create(
                from_=from_wa,
                to=to_wa,
                body=body or '',
            )
        except Exception as exc:
            _logger.exception('Twilio WhatsApp text send failed')
            raise UserError(_('Twilio WhatsApp error: %s') % exc) from exc
        return {'ok': True, 'message_id': message.sid, 'provider': 'twilio', 'raw': message.sid}

    @api.model
    def _twilio_send_media(self, phone, media_url, body=None):
        client, from_wa = self._twilio_client()
        to_wa = self._whatsapp_address(phone)
        kwargs = {
            'from_': from_wa,
            'to': to_wa,
            'media_url': [media_url],
        }
        if body:
            kwargs['body'] = (body or '')[:1600]
        try:
            message = client.messages.create(**kwargs)
        except Exception as exc:
            _logger.exception('Twilio WhatsApp media send failed')
            raise UserError(_('Twilio WhatsApp error: %s') % exc) from exc
        return {'ok': True, 'message_id': message.sid, 'provider': 'twilio', 'raw': message.sid}

    @api.model
    def _twilio_build_content_variables(self, player, db_name=None):
        """
        Build content_variables JSON for the registration Content Template.
        Default maps Twilio sample slots:
          1 = player name, 2 = tournament name
        Override via setting ac_whatsapp.twilio_registration_variables
        (JSON object whose values may use placeholders).
        """
        ICP = self.env['ir.config_parameter'].sudo()
        card_url = player._ac_wa_card_url(db_name=db_name)
        tournament = player.tournament_id
        if tournament and tournament.tournament_type == 'football':
            role_or_pos = (
                player.dominant_position_id.name
                or player.dominant_position_id.code
                or player.role
                or ''
            )
        else:
            role_or_pos = player.role or ''

        values = {
            'name': player.name or 'Player',
            'tournament': tournament.name if tournament else 'Tournament',
            'sl_no': str(player.sl_no or ''),
            'role': role_or_pos,
            'mobile': player.contact or '',
            'email': (player.email or '').strip(),
            'card_url': card_url,
        }

        raw_map = (ICP.get_param('ac_whatsapp.twilio_registration_variables') or '').strip()
        if raw_map:
            try:
                template_map = json.loads(raw_map)
            except Exception as exc:
                raise UserError(_(
                    'Invalid Twilio registration variables JSON in Settings: %s'
                ) % exc) from exc
            out = {}
            for key, pattern in template_map.items():
                text = str(pattern)
                for placeholder, val in values.items():
                    text = text.replace('{{%s}}' % placeholder, val)
                out[str(key)] = text
            return out

        # Default matches typical 2-variable Content Template (like Twilio sample)
        return {
            '1': values['name'],
            '2': values['tournament'],
        }

    @api.model
    def _twilio_send_registration(self, phone, player, db_name=None):
        """
        Send plain text registration confirmation only (no Content Template).
        Content Templates like Twilio's sample appointment SID add buttons and
        replace the body with template copy — not wanted for registration.
        """
        body = player._ac_wa_confirmation_message(db_name=db_name)
        return self._twilio_send_text(phone, body)

    # ══════════════════════════════════════════════════════════════════════
    # Meta Cloud API (kept as alternate provider)
    # ══════════════════════════════════════════════════════════════════════

    @api.model
    def _meta_is_configured(self):
        ICP = self.env['ir.config_parameter'].sudo()
        token = (ICP.get_param('ac_whatsapp.access_token') or '').strip()
        phone_id = (ICP.get_param('ac_whatsapp.phone_number_id') or '').strip()
        return bool(token and phone_id)

    @api.model
    def _meta_credentials(self):
        ICP = self.env['ir.config_parameter'].sudo()
        token = (ICP.get_param('ac_whatsapp.access_token') or '').strip()
        phone_id = (ICP.get_param('ac_whatsapp.phone_number_id') or '').strip()
        if not token or not phone_id:
            raise UserError(_(
                'Meta WhatsApp Cloud API is not configured.\n'
                'Go to Settings → WhatsApp and set Access Token and Phone Number ID, '
                'or switch Provider to Twilio.'
            ))
        return token, phone_id

    @api.model
    def _graph_url(self, path):
        return 'https://graph.facebook.com/%s/%s' % (GRAPH_VERSION, path.lstrip('/'))

    @api.model
    def _raise_api_error(self, response, fallback='WhatsApp API request failed'):
        try:
            data = response.json()
        except Exception:
            data = {}
        err = (data.get('error') or {})
        msg = err.get('message') or response.text or fallback
        code = err.get('code')
        details = err.get('error_data', {}).get('details') or err.get('error_user_msg') or ''
        full = msg
        if details:
            full = '%s\n%s' % (msg, details)
        if code:
            full = '[%s] %s' % (code, full)
        _logger.error('WhatsApp API error: %s | body=%s', full, data)
        raise UserError(_('WhatsApp API error: %s') % full)

    @api.model
    def upload_media_bytes(self, content, filename, mime_type):
        token, phone_id = self._meta_credentials()
        url = self._graph_url('%s/media' % phone_id)
        files = {'file': (filename, io.BytesIO(content), mime_type)}
        data = {'messaging_product': 'whatsapp', 'type': mime_type}
        try:
            resp = requests.post(
                url,
                headers={'Authorization': 'Bearer %s' % token},
                data=data,
                files=files,
                timeout=60,
            )
        except Exception as exc:
            _logger.exception('WhatsApp media upload failed')
            raise UserError(_('Could not reach WhatsApp API: %s') % exc) from exc
        if resp.status_code >= 400:
            self._raise_api_error(resp, 'Media upload failed')
        media_id = (resp.json() or {}).get('id')
        if not media_id:
            raise UserError(_('WhatsApp did not return a media id.'))
        return media_id

    @api.model
    def upload_tournament_poster(self, tournament):
        tournament.ensure_one()
        if not tournament.poster_image:
            raise UserError(_('This tournament has no poster image. Upload one first.'))
        raw = base64.b64decode(tournament.poster_image)
        mime = 'image/jpeg'
        filename = 'tournament_poster.jpg'
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            mime = 'image/png'
            filename = 'tournament_poster.png'
        return self.upload_media_bytes(raw, filename, mime)

    @api.model
    def _meta_send_image(self, phone, media_id=None, image_link=None, caption=None):
        token, phone_id = self._meta_credentials()
        to = self.normalize_phone(phone)
        if not media_id and not image_link:
            raise UserError(_('Image media id or public link is required.'))
        image_payload = {}
        if media_id:
            image_payload['id'] = media_id
        else:
            image_payload['link'] = image_link
        if caption:
            image_payload['caption'] = (caption or '')[:1024]
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'image',
            'image': image_payload,
        }
        return self._meta_send_message(payload)

    @api.model
    def _meta_send_text(self, phone, body):
        to = self.normalize_phone(phone)
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'text',
            'text': {'preview_url': True, 'body': body or ''},
        }
        return self._meta_send_message(payload)

    @api.model
    def _meta_send_message(self, payload):
        token, phone_id = self._meta_credentials()
        url = self._graph_url('%s/messages' % phone_id)
        try:
            resp = requests.post(
                url,
                headers={
                    'Authorization': 'Bearer %s' % token,
                    'Content-Type': 'application/json',
                },
                data=json.dumps(payload),
                timeout=45,
            )
        except Exception as exc:
            _logger.exception('WhatsApp send failed')
            raise UserError(_('Could not reach WhatsApp API: %s') % exc) from exc
        if resp.status_code >= 400:
            self._raise_api_error(resp, 'Send message failed')
        data = resp.json() or {}
        messages = data.get('messages') or []
        wa_id = messages[0].get('id') if messages else False
        return {'ok': True, 'message_id': wa_id, 'provider': 'meta', 'raw': data}
