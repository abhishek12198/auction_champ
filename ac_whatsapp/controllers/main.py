# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp WhatsApp — registration hooks + secure card download
#
##############################################################################
import logging
import secrets

from odoo.http import request

from odoo.addons.auction_module.controllers.main import Auction as AuctionController

_logger = logging.getLogger(__name__)


def _registration_after_create(self, player, db_name):
    """Email + WhatsApp confirmation after free registration create."""
    if not player or not player.exists():
        return None
    try:
        if (player.email or '').strip():
            player.sudo().action_ac_wa_send_registration_email()
    except Exception:
        _logger.exception(
            'ac_whatsapp: registration email failed for player %s', player.id
        )
    try:
        player.sudo()._ac_wa_maybe_send_registration_whatsapp(db_name=db_name)
    except Exception:
        _logger.exception(
            'ac_whatsapp: registration WhatsApp failed for player %s', player.id
        )
    return None


def _registration_success_ctx(self, ctx, tournament, kw):
    """Add WhatsApp share URL + secure card link; send WhatsApp if not yet sent."""
    ctx = dict(ctx or {})
    player_id = ctx.get('player_id')
    if not player_id or not ctx.get('success'):
        return ctx
    player = request.env['auction.team.player'].sudo().browse(player_id)
    if not player.exists():
        return ctx
    db_name = ctx.get('db_name') or request.env.cr.dbname
    try:
        if not player.card_access_token:
            player.sudo().write({'card_access_token': secrets.token_urlsafe(24)})
        # Payment paths create the player without after_create — email / WA here once.
        if (player.email or '').strip() and not player.registration_confirm_sent:
            player.sudo().action_ac_wa_send_registration_email()
            player.invalidate_cache(['registration_confirm_sent'])
        if not player.registration_whatsapp_sent:
            player.sudo()._ac_wa_maybe_send_registration_whatsapp(db_name=db_name)
            player.invalidate_cache(['registration_whatsapp_sent'])
        ctx['whatsapp_confirm_url'] = player._ac_wa_share_url(db_name=db_name)
        ctx['secure_card_url'] = player._ac_wa_card_url(db_name=db_name)
        ctx['player_email'] = player.email or ''
        ctx['registration_confirm_sent'] = bool(player.registration_confirm_sent)
        ctx['registration_whatsapp_sent'] = bool(player.registration_whatsapp_sent)
    except Exception:
        _logger.exception(
            'ac_whatsapp: success ctx failed for player %s', player_id
        )
    return ctx


_orig_player_card_download = AuctionController.player_card_download


def player_card_download(self, db_name, player_id, **kw):
    """Public downloads require a valid card_access_token; logged-in users can bypass."""
    token = (kw.get('token') or '').strip()
    with self._with_db(db_name) as ok:
        if not ok:
            return self._not_found()
        player = request.env['auction.team.player'].sudo().browse(int(player_id))
        if not player.exists():
            return self._not_found()
        expected = (player.card_access_token or '').strip()
        is_public = not request.session.uid
        if expected and is_public and token != expected:
            return request.make_response(
                b'<h1>Invalid or missing card link.</h1>'
                b'<p>Please use the secure download link from your registration confirmation.</p>',
                [('Content-Type', 'text/html; charset=utf-8')],
                status=403,
            )
    return _orig_player_card_download(self, db_name, player_id, **kw)


AuctionController._registration_after_create = _registration_after_create
AuctionController._registration_success_ctx = _registration_success_ctx
AuctionController.player_card_download = player_card_download

# Allow public poster URLs in WhatsApp invitation messages (link preview / open).
_pub_fields = dict(AuctionController._PUBLIC_IMAGE_FIELDS or {})
_t_fields = list(_pub_fields.get('auction.tournament') or [])
if 'poster_image' not in _t_fields:
    _t_fields.append('poster_image')
_pub_fields['auction.tournament'] = _t_fields
AuctionController._PUBLIC_IMAGE_FIELDS = _pub_fields
