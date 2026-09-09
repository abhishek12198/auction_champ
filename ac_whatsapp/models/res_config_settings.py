# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ac_whatsapp_provider = fields.Selection(
        [('twilio', 'Twilio'), ('meta', 'Meta Cloud API')],
        string='WhatsApp Provider',
        config_parameter='ac_whatsapp.provider',
        default='twilio',
        required=True,
    )

    # ── Twilio ────────────────────────────────────────────────────────────
    ac_whatsapp_twilio_account_sid = fields.Char(
        string='Twilio Account SID',
        config_parameter='ac_whatsapp.twilio_account_sid',
        help='From Twilio Console (starts with AC…).',
    )
    ac_whatsapp_twilio_auth_token = fields.Char(
        string='Twilio Auth Token',
        config_parameter='ac_whatsapp.twilio_auth_token',
        help='Auth Token from Twilio Console. Keep secret.',
    )
    ac_whatsapp_twilio_from = fields.Char(
        string='Twilio WhatsApp From',
        config_parameter='ac_whatsapp.twilio_from',
        default='whatsapp:+14155238886',
        help='Sandbox or approved sender, e.g. whatsapp:+14155238886',
    )
    ac_whatsapp_twilio_registration_content_sid = fields.Char(
        string='Registration Content SID',
        config_parameter='ac_whatsapp.twilio_registration_content_sid',
        help='Twilio Content Template SID (HX…) used for player registration confirmations.',
    )
    ac_whatsapp_twilio_registration_variables = fields.Char(
        string='Registration Content Variables (JSON)',
        config_parameter='ac_whatsapp.twilio_registration_variables',
        help='Optional JSON mapping template slots to placeholders, e.g. '
             '{"1":"{{name}}","2":"{{tournament}}"}. '
             'Placeholders: name, tournament, sl_no, role, mobile, email, card_url. '
             'Default is {"1":"{{name}}","2":"{{tournament}}}.',
    )
    ac_whatsapp_twilio_inbound_reply = fields.Char(
        string='Inbound auto-reply text',
        config_parameter='ac_whatsapp.twilio_inbound_reply',
        default='Message received! Thanks for contacting AuctionChamp.',
        help='TwiML reply body for POST /ac_whatsapp/twilio/reply',
    )

    # ── Meta (optional) ───────────────────────────────────────────────────
    ac_whatsapp_access_token = fields.Char(
        string='Meta Access Token',
        config_parameter='ac_whatsapp.access_token',
        help='Permanent or temporary System User token from Meta Developer Console.',
    )
    ac_whatsapp_phone_number_id = fields.Char(
        string='Meta Phone Number ID',
        config_parameter='ac_whatsapp.phone_number_id',
        help='WhatsApp Cloud API Phone Number ID (not the +91 number).',
    )
    ac_whatsapp_business_account_id = fields.Char(
        string='Meta WABA ID',
        config_parameter='ac_whatsapp.waba_id',
        help='Optional. WABA ID from Meta Business Suite.',
    )

    ac_whatsapp_default_country_code = fields.Char(
        string='Default country code',
        config_parameter='ac_whatsapp.default_country_code',
        default='91',
        help='Used when recipients enter a 10-digit local mobile (e.g. 91 for India).',
    )
    ac_whatsapp_auto_send_registration = fields.Boolean(
        string='Auto-send registration WhatsApp',
        config_parameter='ac_whatsapp.auto_send_registration',
        default=True,
        help='After a successful /player/register, send a WhatsApp confirmation '
             'to the player mobile (Twilio Content Template when SID is set).',
    )
