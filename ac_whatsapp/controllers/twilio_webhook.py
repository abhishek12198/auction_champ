# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — Twilio inbound webhook (TwiML reply)
#
##############################################################################
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from twilio.twiml.messaging_response import MessagingResponse
except ImportError:  # pragma: no cover
    MessagingResponse = None


class AcWhatsappTwilioController(http.Controller):

    @http.route(
        '/ac_whatsapp/twilio/reply',
        type='http',
        auth='public',
        methods=['POST', 'GET'],
        csrf=False,
    )
    def reply_whatsapp(self, **kw):
        """
        Twilio Sandbox / WhatsApp "WHEN A MESSAGE COMES IN" webhook.
        Equivalent to Twilio's Flask MessagingResponse sample.
        """
        ICP = request.env['ir.config_parameter'].sudo()
        reply_text = (
            ICP.get_param('ac_whatsapp.twilio_inbound_reply')
            or 'Message received! Thanks for contacting AuctionChamp.'
        ).strip()

        # Log inbound for debugging (From / Body are Twilio form fields)
        try:
            vals = request.httprequest.form or request.params
            _logger.info(
                'Twilio WhatsApp inbound From=%s Body=%s',
                vals.get('From'),
                (vals.get('Body') or '')[:200],
            )
        except Exception:
            pass

        if MessagingResponse is not None:
            resp = MessagingResponse()
            resp.message(reply_text)
            twiml = str(resp)
        else:
            # Minimal TwiML without the SDK
            safe = (
                reply_text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
            )
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Response><Message>%s</Message></Response>' % safe
            )

        return request.make_response(
            twiml,
            headers=[('Content-Type', 'text/xml; charset=utf-8')],
        )
