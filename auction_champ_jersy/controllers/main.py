# -*- coding: utf-8 -*-
import base64
import logging
from contextlib import contextmanager

import odoo
import werkzeug
from odoo import SUPERUSER_ID, api, http
from odoo.http import request

_logger = logging.getLogger(__name__)

VALID_SIZES = {'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'}
VALID_SLEEVES = {'F', 'H'}
PUBLIC_IMAGE_FIELDS = ('team_logo', 'sponsor_logo', 'jersey_design')


class AuctionChampJerseyController(http.Controller):
    """Public jersey survey — same db-prefixed / auth='none' pattern as player register."""

    @contextmanager
    def _with_db(self, db_name):
        """Open a cursor for *db_name* and inject it into the current request."""
        try:
            registry = odoo.registry(db_name)
        except Exception:
            yield False
            return

        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            old_cr, old_uid, old_env, old_context = (
                request._cr, request._uid, request._env, request._context
            )
            request._cr = cr
            request._uid = SUPERUSER_ID
            request._context = {}
            request._env = env
            try:
                yield True
            finally:
                request._cr = old_cr
                request._uid = old_uid
                request._env = old_env
                request._context = old_context

    def _not_found(self):
        return request.make_response(
            '<html><head><title>404 Not Found</title></head>'
            '<body><h1>Survey not found</h1>'
            '<p>This jersey collection link is invalid or inactive.</p></body></html>',
            headers=[('Content-Type', 'text/html; charset=utf-8')],
            status=404,
        )

    def _find_team(self, slug):
        return request.env['auction.champ.jersey.team'].sudo().search([
            ('slug', '=', slug),
            ('active', '=', True),
        ], limit=1)

    def _resolve_db_for_slug(self, slug):
        """Pick the DB that contains this jersey team slug (multi-db safe)."""
        from odoo.http import db_list, db_monodb
        mono = db_monodb(request.httprequest)
        candidates = []
        if mono:
            candidates.append(mono)
        try:
            for db in db_list(force=True, httprequest=request.httprequest):
                if db not in candidates:
                    candidates.append(db)
        except Exception:
            pass
        for db in candidates:
            try:
                registry = odoo.registry(db)
            except Exception:
                continue
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    if 'auction.champ.jersey.team' not in env:
                        continue
                    match = env['auction.champ.jersey.team'].sudo().search([
                        ('slug', '=', slug),
                        ('active', '=', True),
                    ], limit=1)
                    if match:
                        return db
            except Exception:
                continue
        return mono or (candidates[0] if candidates else None)

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
        rec = record.with_context(bin_size=False).sudo()
        binary = rec[field]
        if not binary:
            return b''
        try:
            if isinstance(binary, bytes):
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

    def _img_url(self, db_name, team, field):
        rec = team.with_context(bin_size=False).sudo()
        if not rec[field]:
            return ''
        return '/%s/auction/jersey/image/%d/%s' % (db_name, team.id, field)

    def _survey_values(self, db_name, team, **extra):
        players = team.player_ids.sorted(lambda p: p.id)
        return {
            'db_name': db_name,
            'team': team,
            'players': players,
            'player_count': len(players),
            'team_logo_uri': self._img_url(db_name, team, 'team_logo'),
            'sponsor_logo_uri': self._img_url(db_name, team, 'sponsor_logo'),
            'jersey_design_uri': self._img_url(db_name, team, 'jersey_design'),
            'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
            'error': extra.get('error'),
            'form': extra.get('form') or {},
            'success': extra.get('success', False),
            'ack_player': extra.get('ack_player'),
        }

    def _render_survey(self, db_name, team, **extra):
        html = request.render(
            'auction_champ_jersy.jersey_survey_template',
            self._survey_values(db_name, team, **extra),
            lazy=False,
        )
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    # ── Legacy redirect (no db prefix) ───────────────────────────────────────

    @http.route('/auction/jersey/<string:slug>', type='http', auth='none',
                website=False, methods=['GET', 'POST'], csrf=False)
    def jersey_survey_legacy(self, slug, **kw):
        """Redirect old /auction/jersey/<slug> to /<db>/auction/jersey/<slug>."""
        db_name = self._resolve_db_for_slug(slug)
        if not db_name:
            return self._not_found()
        target = '/%s/auction/jersey/%s' % (db_name, slug)
        qs = request.httprequest.query_string
        if qs:
            target = '%s?%s' % (target, qs.decode('utf-8') if isinstance(qs, bytes) else qs)
        return werkzeug.utils.redirect(target, 301)

    @http.route(
        '/auction/jersey/image/<int:team_id>/<string:field>',
        type='http', auth='none', website=False, csrf=False,
    )
    def jersey_public_image_legacy(self, team_id, field, **kw):
        from odoo.http import db_list, db_monodb
        db_name = db_monodb(request.httprequest)
        if not db_name:
            dbs = db_list(force=True, httprequest=request.httprequest)
            db_name = dbs[0] if dbs else None
        if not db_name:
            return self._not_found()
        return werkzeug.utils.redirect(
            '/%s/auction/jersey/image/%d/%s' % (db_name, team_id, field), 301
        )

    # ── Canonical db-prefixed routes ─────────────────────────────────────────

    @http.route(
        '/<string:db_name>/auction/jersey/image/<int:team_id>/<string:field>',
        type='http', auth='none', website=False, csrf=False,
    )
    def jersey_public_image(self, db_name, team_id, field, **kw):
        """Serve team logo / sponsor / jersey design for the public survey."""
        if field not in PUBLIC_IMAGE_FIELDS:
            return self._not_found()

        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            team = request.env['auction.champ.jersey.team'].sudo().browse(team_id)
            if not team.exists() or not team.active:
                return self._not_found()

            image_bytes = self._read_binary(team, field)
            if not image_bytes:
                return self._not_found()

            return request.make_response(image_bytes, headers=[
                ('Content-Type', self._image_mimetype(image_bytes)),
                ('Cache-Control', 'public, max-age=300'),
            ])

    @http.route(
        '/<string:db_name>/auction/jersey/<string:slug>',
        type='http', auth='none', website=False,
        methods=['GET', 'POST'], csrf=False,
    )
    def jersey_survey(self, db_name, slug, **kw):
        with self._with_db(db_name) as ok:
            if not ok:
                return self._not_found()

            team = self._find_team(slug)
            if not team:
                return self._not_found()

            if request.httprequest.method == 'POST':
                return self._handle_submit(db_name, team, **kw)

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

            return self._render_survey(
                db_name, team, success=success, ack_player=ack_player,
            )

    def _handle_submit(self, db_name, team, **kw):
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
            return self._render_survey(db_name, team, error=error, form=form)

        player = request.env['auction.champ.jersey.player'].sudo().create({
            'team_id': team.id,
            'player_name': player_name,
            'number': number or False,
            'size': size,
            'sleeve': sleeve,
        })

        return werkzeug.utils.redirect(
            '/%s/auction/jersey/%s?submitted=1&entry=%d' % (db_name, team.slug, player.id),
            303,
        )
