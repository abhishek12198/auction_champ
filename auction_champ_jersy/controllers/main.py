# -*- coding: utf-8 -*-
import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

VALID_SIZES = {'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'}
VALID_SLEEVES = {'F', 'H'}
PUBLIC_IMAGE_FIELDS = ('team_logo', 'sponsor_logo', 'jersey_design')


class AuctionChampJerseyController(http.Controller):

    def _find_team(self, slug):
        return request.env['auction.champ.jersey.team'].sudo().search([
            ('slug', '=', slug),
            ('active', '=', True),
        ], limit=1)

    @staticmethod
    def _image_mimetype(image_bytes):
        if not image_bytes:
            return 'application/octet-stream'
        if image_bytes[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/jpeg'

    def _read_binary(self, record, field):
        """Read raw image bytes from a Binary field (handles attachment storage)."""
        if field not in PUBLIC_IMAGE_FIELDS:
            return b''
        # Avoid bin_size mode which returns "12.3 Kb" instead of data
        rec = record.with_context(bin_size=False).sudo()
        binary = rec[field]
        if not binary:
            return b''
        try:
            if isinstance(binary, bytes):
                # May already be raw or base64 bytes
                try:
                    return base64.b64decode(binary)
                except Exception:
                    return binary
            if isinstance(binary, str):
                return base64.b64decode(binary)
        except Exception:
            _logger.exception('Failed to decode jersey image %s/%s', record.id, field)
            return b''
        return b''

    def _img_url(self, team, field):
        rec = team.with_context(bin_size=False).sudo()
        if not rec[field]:
            return ''
        return '/auction/jersey/image/%d/%s' % (team.id, field)

    def _survey_values(self, team, **extra):
        players = team.player_ids.sorted(lambda p: p.id)
        return {
            'team': team,
            'players': players,
            'player_count': len(players),
            'team_logo_uri': self._img_url(team, 'team_logo'),
            'sponsor_logo_uri': self._img_url(team, 'sponsor_logo'),
            'jersey_design_uri': self._img_url(team, 'jersey_design'),
            'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
            'error': extra.get('error'),
            'form': extra.get('form') or {},
            'success': extra.get('success', False),
            'ack_player': extra.get('ack_player'),
        }

    @http.route(
        '/auction/jersey/image/<int:team_id>/<string:field>',
        type='http', auth='public', website=False, csrf=False,
    )
    def jersey_public_image(self, team_id, field, **kw):
        """Serve team logo / sponsor / jersey design for the public survey."""
        if field not in PUBLIC_IMAGE_FIELDS:
            return request.not_found()

        team = request.env['auction.champ.jersey.team'].sudo().browse(team_id)
        if not team.exists() or not team.active:
            return request.not_found()

        image_bytes = self._read_binary(team, field)
        if not image_bytes:
            return request.not_found()

        return request.make_response(image_bytes, headers=[
            ('Content-Type', self._image_mimetype(image_bytes)),
            ('Cache-Control', 'public, max-age=300'),
        ])

    @http.route('/auction/jersey/<string:slug>', type='http', auth='public',
                website=False, methods=['GET', 'POST'], csrf=False)
    def jersey_survey(self, slug, **kw):
        team = self._find_team(slug)
        if not team:
            return request.make_response(
                '<h1>Survey not found</h1><p>This jersey collection link is invalid or inactive.</p>',
                headers=[('Content-Type', 'text/html; charset=utf-8')],
                status=404,
            )

        if request.httprequest.method == 'POST':
            return self._handle_submit(team, **kw)

        # PRG acknowledgement: ?submitted=1&entry=<id>
        ack_player = None
        success = False
        if kw.get('submitted') == '1' and kw.get('entry'):
            try:
                entry_id = int(kw.get('entry'))
            except (TypeError, ValueError):
                entry_id = 0
            if entry_id:
                player = request.env['auction.champ.jersey.player'].sudo().browse(entry_id)
                if player.exists() and player.team_id.id == team.id:
                    ack_player = player
                    success = True

        return request.render(
            'auction_champ_jersy.jersey_survey_template',
            self._survey_values(team, success=success, ack_player=ack_player),
        )

    def _handle_submit(self, team, **kw):
        player_name = (kw.get('player_name') or '').strip()
        number = (kw.get('number') or '').strip()
        size = (kw.get('size') or '').strip().upper()
        sleeve = (kw.get('sleeve') or '').strip().upper()

        form = {
            'player_name': player_name,
            'number': number,
            'size': size,
            'sleeve': sleeve,
        }

        error = None
        if not player_name:
            error = 'Please enter the name to print on the jersey.'
        elif size not in VALID_SIZES:
            error = 'Please select a valid size.'
        elif sleeve not in VALID_SLEEVES:
            error = 'Please select sleeve type (Full or Half).'

        if error:
            return request.render(
                'auction_champ_jersy.jersey_survey_template',
                self._survey_values(team, error=error, form=form),
            )

        player = request.env['auction.champ.jersey.player'].sudo().create({
            'team_id': team.id,
            'player_name': player_name,
            'number': number or False,
            'size': size,
            'sleeve': sleeve,
        })

        # Redirect to GET so theme toggle / refresh keeps acknowledgement + table
        return request.redirect(
            '/auction/jersey/%s?submitted=1&entry=%d' % (team.slug, player.id)
        )
